"""Business accounts: organizations, members, invitations and payments out of the business cashbook.

Every action checks the caller's role (organizations.roles) and writes an audit event in the same
transaction. Lock order: organization row, then payment row, then beneficiary row, then accounts, then audit.
"""
import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.dispatch import receiver
from django.utils import timezone
from rest_framework import status

from accounting import business as business_books
from accounting.models import BusinessEntry
from audit.services import record
from banking.models import Account
from banking.services import (
    BOOKED_BY_CALLER,
    holder_name,
    new_reference,
    reverse_transfer,
    transfer_from_organization,
)
from fluxpay.exceptions import BusinessError
from payments import services as payment_services
from payments.providers import get_provider
from payments.signals import payment_settled
from payroll.models import Worker
from platform_settings import services as rules

from . import beneficiaries
from .models import Beneficiary, Invitation, Membership, Organization, Payment
from .roles import Perm, Role, can_manage, has_perm

P = Payment.Status
# Looking, not acting: allowed without two-step verification.
READ_ONLY = {Perm.VIEW, Perm.VIEW_AUDIT}


# --- Access -------------------------------------------------------------------------------------


def membership_for(user, organization_id, perm: Perm) -> Membership:
    """The caller's active membership, if their role allows `perm`.

    Non-members get 404 (not 403) so the API never reveals which businesses exist.
    """
    membership = (
        Membership.objects.select_related("organization")
        .filter(organization_id=organization_id, user=user, is_active=True)
        .first()
    )
    if membership is None:
        raise BusinessError("Business not found.", "organization_not_found", status.HTTP_404_NOT_FOUND)
    if not has_perm(membership.role, perm):
        raise BusinessError("Your role doesn't allow this.", "permission_denied", status.HTTP_403_FORBIDDEN)
    if perm != Perm.VIEW and membership.organization.status != Organization.Status.ACTIVE:
        raise BusinessError("This business is suspended.", "organization_suspended", status.HTTP_403_FORBIDDEN)
    if (
        perm not in READ_ONLY
        and membership.role in (Role.OWNER, Role.ADMIN)
        and settings.FLUXPAY_REQUIRE_BUSINESS_MFA
        and not user.mfa_enabled
    ):
        # Owners and admins can move the business's money and change who it pays: a password alone isn't enough.
        raise BusinessError(
            "Turn on two-step verification (Settings > Security) to manage this business.",
            "mfa_required",
            status.HTTP_403_FORBIDDEN,
        )
    return membership


# --- Organizations ------------------------------------------------------------------------------


@db_transaction.atomic
def create_organization(*, user, name: str, registration_number: str = "", currency: str | None = None):
    """Creates the business, makes the creator its owner and opens its first wallet (with no bonus)."""
    organization = Organization.objects.create(name=name, registration_number=registration_number, created_by=user)
    Membership.objects.create(organization=organization, user=user, role=Role.OWNER)
    Account.objects.create(
        owner=user,
        organization=organization,
        currency=rules.currency(currency or rules.platform().default_currency_id).code,
        name="Business Wallet",
    )
    record("org.created", actor=user, organization_id=organization.id, target=organization, metadata={"name": name})
    return organization


def onboard_business(*, staff, name: str, owner_email: str, owner_name: str, owner_phone: str = "",
                     registration_number: str = "") -> tuple[Organization, bool]:  # fmt: skip
    """FluxPay staff set up a business for its owner. Returns (business, owner_is_new).

    A new owner gets a FluxPay account (and personal wallet) with no password, and an email with a link to set
    one; someone who already uses FluxPay just finds the business in their app. Recorded as done by staff.
    """
    from django.contrib.auth import get_user_model
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    from banking.services import open_wallet

    User = get_user_model()
    name, owner_email, owner_name = name.strip(), owner_email.strip().lower(), owner_name.strip()
    if not name:
        raise BusinessError("Give the business a name.", "name_required")
    if Organization.objects.filter(name__iexact=name).exists():
        raise BusinessError(f"There is already a business called {name}.", "duplicate_business")
    with db_transaction.atomic():
        owner = User.objects.filter(email__iexact=owner_email).first()
        is_new = owner is None
        if is_new:
            if not owner_name:
                raise BusinessError("Give the owner's full name.", "owner_name_required")
            owner = User.objects.create_user(owner_email, None, full_name=owner_name, phone_number=owner_phone.strip())
            open_wallet(owner)
        elif not owner.is_active:
            raise BusinessError("That person's FluxPay account is disabled.", "owner_inactive")
        elif owner.is_staff:
            raise BusinessError("FluxPay staff accounts can't own a business.", "owner_is_staff")
        organization = create_organization(user=owner, name=name, registration_number=registration_number.strip())
        record("org.onboarded", actor=staff, organization_id=organization.id, target=organization,
               metadata={"name": name, "owner": owner.email, "new_owner": is_new, "by_staff": True})  # fmt: skip
        # A new owner, or one onboarded before who never chose a password, needs the link to choose one.
        if not owner.has_usable_password():
            link = settings.PASSWORD_RESET_LINK.format(
                uid=urlsafe_base64_encode(force_bytes(owner.pk)), token=default_token_generator.make_token(owner)
            )
            body = (f"Hi {owner.full_name},\n\nFluxPay has set up {name} for you. Open this link to choose your "
                    f"password:\n{link}\n\nThen install the FluxPay app and sign in with {owner.email}. Your "
                    f"business is under the Business tab, where you can pay workers and suppliers and keep its "
                    f"books.")  # fmt: skip
        else:
            body = (f"Hi {owner.full_name},\n\nFluxPay has set up {name} for you. Open the FluxPay app, sign in "
                    f"with {owner.email} and go to the Business tab to start paying workers and suppliers and keeping "
                    f"its books.\n\nForgot your password? Tap \"Forgot password?\" on the sign-in screen.")  # fmt: skip
        email = owner.email
        db_transaction.on_commit(
            lambda: send_mail(subject=f"{name} is ready on FluxPay", message=body, from_email=None,
                              recipient_list=[email], fail_silently=True),
            robust=True,
        )
    return organization, is_new


def update_settings(*, membership: Membership, **changes) -> Organization:
    """Changes name, registration_number or approval_threshold. Owners only (Perm.MANAGE_SETTINGS)."""
    allowed = {"name", "registration_number", "approval_threshold"}
    with db_transaction.atomic():
        organization = Organization.objects.select_for_update().get(id=membership.organization_id)
        before, after = {}, {}
        for field, value in changes.items():
            if field not in allowed or getattr(organization, field) == value:
                continue
            before[field], after[field] = str(getattr(organization, field)), str(value)
            setattr(organization, field, value)
        if after:
            organization.save(update_fields=[*after, "updated_at"])
            record(
                "org.settings_changed",
                actor=membership.user,
                organization_id=organization.id,
                target=organization,
                metadata={"before": before, "after": after},
            )
    return organization


# --- Members and invitations ----------------------------------------------------------------------


def invite_member(*, membership: Membership, email: str, role: str) -> tuple[Invitation, str]:
    """Emails an invitation. Returns (invitation, token); the token is never stored, only its hash."""
    if not can_manage(membership.role, role):
        raise BusinessError(f"Your role can't invite {role.lower()} members.", "permission_denied", 403)
    email = email.strip().lower()
    organization = membership.organization
    if Membership.objects.filter(organization=organization, user__email__iexact=email, is_active=True).exists():
        raise BusinessError("That person is already a member.", "already_member")

    token = secrets.token_urlsafe(32)
    with db_transaction.atomic():
        # A new invitation replaces any pending one for the same address.
        Invitation.objects.filter(
            organization=organization, email=email, accepted_at__isnull=True, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())
        invitation = Invitation.objects.create(
            organization=organization,
            email=email,
            role=role,
            token_hash=_hash_token(token),
            invited_by=membership.user,
            expires_at=timezone.now() + timedelta(days=rules.platform().invitation_expiry_days),
        )
        record(
            "org.member.invited",
            actor=membership.user,
            organization_id=organization.id,
            target=invitation,
            metadata={"email": email, "role": role},
        )
        link = settings.ORG_INVITE_LINK.format(token=token)
        db_transaction.on_commit(
            lambda: _send_invitation(organization, membership.user, email, role, link), robust=True
        )
    return invitation, token


def revoke_invitation(*, membership: Membership, invitation_id) -> Invitation:
    with db_transaction.atomic():
        invitation = (
            Invitation.objects.select_for_update()
            .filter(id=invitation_id, organization_id=membership.organization_id)
            .first()
        )
        if invitation is None or invitation.accepted_at or invitation.revoked_at:
            raise BusinessError("No pending invitation with that id.", "invitation_not_found", 404)
        if not can_manage(membership.role, invitation.role):
            raise BusinessError("Your role can't manage this invitation.", "permission_denied", 403)
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
        record("org.invitation.revoked", actor=membership.user, organization_id=invitation.organization_id,
               target=invitation, metadata={"email": invitation.email})
    return invitation


def accept_invitation(*, user, token: str) -> Membership:
    with db_transaction.atomic():
        invitation = (
            Invitation.objects.select_for_update().select_related("organization")
            .filter(token_hash=_hash_token(token))
            .first()
        )
        if (
            invitation is None
            or invitation.accepted_at
            or invitation.revoked_at
            or invitation.expires_at <= timezone.now()
        ):
            raise BusinessError("This invitation is invalid or has expired.", "invitation_invalid")
        if invitation.email != user.email.lower():
            raise BusinessError("This invitation was sent to a different email address.", "invitation_email_mismatch", 403)

        Organization.objects.select_for_update().get(id=invitation.organization_id)
        membership = Membership.objects.filter(organization=invitation.organization, user=user).first()
        if membership and membership.is_active:
            raise BusinessError("You're already a member of this business.", "already_member")
        if membership:  # rejoining after being removed
            membership.role, membership.is_active, membership.invited_by = invitation.role, True, invitation.invited_by
            membership.save(update_fields=["role", "is_active", "invited_by", "updated_at"])
        else:
            membership = Membership.objects.create(
                organization=invitation.organization, user=user, role=invitation.role, invited_by=invitation.invited_by
            )
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at"])
        record("org.member.joined", actor=user, organization_id=invitation.organization_id, target=membership,
               metadata={"role": membership.role})
    return membership


def change_role(*, membership: Membership, target_id, role: str) -> Membership:
    with db_transaction.atomic():
        Organization.objects.select_for_update().get(id=membership.organization_id)  # serialises member changes
        target = _active_member(membership, target_id)
        if target.id == membership.id:
            raise BusinessError("You can't change your own role. Ask another owner.", "own_role")
        if not (can_manage(membership.role, target.role) and can_manage(membership.role, role)):
            raise BusinessError("Your role can't make this change.", "permission_denied", 403)
        if target.role == role:
            return target
        if target.role == Role.OWNER:
            _keep_an_owner(membership.organization_id)
        previous, target.role = target.role, role
        target.save(update_fields=["role", "updated_at"])
        record("org.member.role_changed", actor=membership.user, organization_id=membership.organization_id,
               target=target, metadata={"email": target.user.email, "from": previous, "to": role})
    return target


def remove_member(*, membership: Membership, target_id) -> Membership:
    """Removes someone (or yourself, to leave). The last owner can't be removed."""
    with db_transaction.atomic():
        Organization.objects.select_for_update().get(id=membership.organization_id)
        target = _active_member(membership, target_id)
        if target.id != membership.id and not can_manage(membership.role, target.role):
            raise BusinessError("Your role can't remove this member.", "permission_denied", 403)
        if target.role == Role.OWNER:
            _keep_an_owner(membership.organization_id)
        target.is_active = False
        target.save(update_fields=["is_active", "updated_at"])
        record("org.member.removed", actor=membership.user, organization_id=membership.organization_id,
               target=target, metadata={"email": target.user.email, "role": target.role})
    return target


# --- Payments -----------------------------------------------------------------------------------

T = Payment.Type

# Where each type of payment is filed in the business's books, unless the payer chose a category.
BOOKS_ROLE = {
    T.SALARY: "salaries",
    T.ALLOWANCE: "allowances",
    T.BONUS: "bonuses",
    T.COMMISSION: "commissions",
    T.OTHER_WORKER: "salaries",
    T.SUPPLIER: "suppliers",
    T.VENDOR: "suppliers",
    T.CONTRACTOR: "contractors",
    T.EXPENSE: "expenses",
    T.WITHDRAWAL: "drawings",
    T.OTHER: "expenses",
}
# How each external payout method is sent: (rail, payments.ExternalPayment.Method).
PAYOUT_METHODS = {
    Beneficiary.Method.MPESA_MOBILE: ("MPESA", "MPESA_B2C"),
    Beneficiary.Method.MPESA_PAYBILL: ("MPESA", "MPESA_PAYBILL"),
    Beneficiary.Method.MPESA_TILL: ("MPESA", "MPESA_TILL"),
    Beneficiary.Method.BANK: ("BANK", "BANK_OUT"),
}


def books_role(payment: Payment) -> str:
    return payment.books_category or BOOKS_ROLE[payment.type]


def cashbook(organization) -> Account:
    """The business's one wallet: every payment comes out of it."""
    wallet = Account.objects.filter(organization=organization, is_active=True).first()
    if wallet is None:
        raise BusinessError("This business's cashbook is closed.", "account_not_found", 404)
    return wallet


def create_payment(*, membership: Membership, amount: Decimal, note: str, idempotency_key: str, type: str = "",
                   worker_id=None, beneficiary_id=None, destination_account_number: str = "",
                   books_category: str = "") -> tuple[Payment, bool]:
    """Records a payment from the business cashbook: to one of its workers (the worker types), to a saved
    beneficiary (`type` defaults from its kind) or to any FluxPay account. Up to the approval threshold it is
    sent straight away; above it, it waits."""
    user, organization = membership.user, membership.organization
    existing = Payment.objects.filter(created_by=user, idempotency_key=idempotency_key).first()
    if existing:
        return existing, False
    source = cashbook(organization)
    rules.check_amount(amount, source.currency)
    beneficiary = None
    if beneficiary_id:
        beneficiary = beneficiaries.payable(organization, beneficiary_id)
        type = type or beneficiaries.PAYMENT_TYPE[beneficiary.kind]
        books_category = books_category or beneficiary.books_category
        if type in Payment.WORKER_TYPES:
            raise BusinessError("Salaries and other worker payments go to a worker, not a beneficiary.", "invalid_type")
        if beneficiary.method in PAYOUT_METHODS:  # fail now, not after approval, if the rail can't take it
            rail = PAYOUT_METHODS[beneficiary.method][0]
            payment_services.check_payable_amount(rail, amount, source.currency)
            if not get_provider(rail).can_pay_out():
                raise BusinessError(f"Payouts by {beneficiary.get_method_display()} aren't available yet.", "rail_unavailable")
        destination_account_number = beneficiary.account_number
    if not type:
        raise BusinessError("Choose what the payment is for.", "type_required")
    if type == T.WITHDRAWAL and not has_perm(membership.role, Perm.WITHDRAW):
        raise BusinessError("Only an owner can take money out of the business.", "permission_denied", 403)
    if beneficiary and beneficiary.method in PAYOUT_METHODS:
        worker, recipient = None, None
    else:
        worker, recipient = _recipient(organization, type, worker_id, destination_account_number)

    try:
        with db_transaction.atomic():
            payment = Payment.objects.create(
                organization=organization,
                source_account=source,
                type=type,
                worker=worker,
                beneficiary=beneficiary,
                beneficiary_details=beneficiary.payout_details() if beneficiary else {},
                destination_account_number=recipient.account_number if recipient else "",
                recipient_name=beneficiary.name if beneficiary else holder_name(recipient),
                amount=amount,
                note=note,
                books_category=books_category,
                reference=new_reference(),
                status=P.PENDING_APPROVAL if amount > organization.approval_threshold else P.PENDING,
                created_by=user,
                idempotency_key=idempotency_key,
            )
            if payment.status == P.PENDING:
                _execute(payment, actor=user)  # locks accounts, so it runs before this transaction's first audit event
            record("org.payment.created", actor=user, organization_id=organization.id, target=payment,
                   metadata=_payment_metadata(payment))
            _record_outcome(payment, actor=user)
    except IntegrityError:
        return Payment.objects.get(created_by=user, idempotency_key=idempotency_key), False
    return payment, True


def approve_payment(*, membership: Membership, payment_id, note: str = "") -> Payment:
    """A second person approves, and the payment is sent. The creator can never approve their own."""
    with db_transaction.atomic():
        payment = _pending_approval(membership, payment_id)
        if payment.created_by_id == membership.user_id:
            raise BusinessError("You can't approve a payment you created.", "self_approval", 403)
        payment.decided_by, payment.decided_at, payment.decision_note = membership.user, timezone.now(), note[:255]
        payment.status = P.PENDING
        payment.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
        _execute(payment, actor=payment.created_by)
        record("org.payment.approved", actor=membership.user, organization_id=payment.organization_id,
               target=payment, metadata=_payment_metadata(payment))
        _record_outcome(payment, actor=membership.user)
    return payment


def reject_payment(*, membership: Membership, payment_id, note: str = "") -> Payment:
    with db_transaction.atomic():
        payment = _pending_approval(membership, payment_id)
        payment.status, payment.decided_by, payment.decided_at = P.REJECTED, membership.user, timezone.now()
        payment.decision_note = note[:255]
        payment.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
        record("org.payment.rejected", actor=membership.user, organization_id=payment.organization_id,
               target=payment, metadata={**_payment_metadata(payment), "note": payment.decision_note})
    return payment


def cancel_payment(*, membership: Membership, payment_id) -> Payment:
    """The creator withdraws a payment that hasn't been decided yet."""
    with db_transaction.atomic():
        payment = _pending_approval(membership, payment_id)
        if payment.created_by_id != membership.user_id:
            raise BusinessError("Only the person who created this payment can cancel it.", "permission_denied", 403)
        payment.status = P.CANCELLED
        payment.save(update_fields=["status", "updated_at"])
        record("org.payment.cancelled", actor=membership.user, organization_id=payment.organization_id,
               target=payment, metadata=_payment_metadata(payment))
    return payment


def deposit_by_mpesa(*, membership: Membership, phone_number: str, amount: Decimal, idempotency_key: str):
    """Sends an STK Push to `phone_number`; the cashbook is credited once M-Pesa confirms. Returns (payment, created)."""
    return payment_services.deposit_into(
        cashbook(membership.organization), initiator=membership.user, rail="MPESA", method="MPESA_STK",
        amount=amount, idempotency_key=idempotency_key, metadata={"phone_number": phone_number},
    )  # fmt: skip


def send_payment(payment: Payment, *, actor) -> None:
    """Moves the money for one PENDING payment (its row locked by the caller) and marks it paid.

    Raises BusinessError if it can't be paid: a payment on its own then fails by itself (`_execute`), while a
    pay run is paid all or nothing. A pay run's payslips are booked as payroll, one cashbook line each.
    A beneficiary paid by M-Pesa or bank: the money leaves the cashbook now and the payment is PROCESSING
    until the provider confirms it (`on_payout_settled`).
    """
    in_run = payment.pay_run_id is not None
    if payment.beneficiary_id:  # still verified, and still the details it was created with
        beneficiary = Beneficiary.objects.select_for_update().get(pk=payment.beneficiary_id)  # vs. an edit right now
        beneficiaries.check_payable(beneficiary, payment.beneficiary_details)
        if beneficiary.method in PAYOUT_METHODS:
            _send_payout(payment, beneficiary, actor=actor)
            return
    transfer, _debit, _created = transfer_from_organization(
        initiator=actor,
        organization=payment.organization,
        source_id=payment.source_account_id,
        destination_number=payment.destination_account_number,
        amount=payment.amount,
        note=payment.note or payment.get_type_display(),
        idempotency_key=f"payment-{payment.id}",
        reference=payment.reference,
        books_role=BOOKED_BY_CALLER if in_run else books_role(payment),
    )
    if in_run:
        business_books.record_movement(
            wallet=transfer.source, direction="OUT", amount=payment.amount, source=BusinessEntry.Source.PAYROLL,
            reference=payment.reference, counterparty=payment.recipient_name,
            counterparty_account=payment.destination_account_number, description=transfer.note,
            role=books_role(payment), actor=actor,
        )  # fmt: skip
    payment.status, payment.transfer, payment.completed_at = P.COMPLETED, transfer, timezone.now()
    payment.save(update_fields=["status", "transfer", "completed_at", "updated_at"])


def _send_payout(payment: Payment, beneficiary: Beneficiary, *, actor) -> None:
    rail, method = PAYOUT_METHODS[beneficiary.method]
    label = payment.note or f"{payment.get_type_display()} to {beneficiary.name}"
    external = payment_services.hold_payout(
        Account.objects.get(pk=payment.source_account_id),
        initiator=actor,
        rail=rail,
        method=method,
        amount=payment.amount,
        idempotency_key=f"payment-{payment.id}",
        reference=payment.reference,
        metadata={
            **payment.beneficiary_details,
            "recipient": beneficiary.name,
            "description": label[:140],
            "remarks": label[:100],
            "books_role": books_role(payment),
        },
    )
    payment.status, payment.external_payment = P.PROCESSING, external
    payment.save(update_fields=["status", "external_payment", "updated_at"])


@receiver(payment_settled)
def on_payout_settled(sender, payment, **kwargs):
    """A business payment sent by M-Pesa or bank is paid, or failed (its money is already back in the cashbook)."""
    business_payment = Payment.objects.select_for_update().filter(external_payment=payment).first()
    if business_payment is None or business_payment.status != P.PROCESSING:
        return
    if payment.status == payment.Status.COMPLETED:
        business_payment.status, business_payment.completed_at = P.COMPLETED, timezone.now()
    else:
        business_payment.status = P.FAILED
        business_payment.failure_reason = f"{payment.get_rail_display()}: {payment.failure_reason}"[:255]
    business_payment.save(update_fields=["status", "completed_at", "failure_reason", "updated_at"])
    _record_outcome(business_payment, actor=None)


def reverse_payment(*, membership: Membership, payment_id, reason: str) -> Payment:
    """Takes back a payment made in error, while the recipient still holds the money and within the
    platform's reversal window. The money goes back into the cashbook; the payment is kept, marked REVERSED."""
    if not has_perm(membership.role, Perm.APPROVE_PAYMENT):
        raise BusinessError("Your role doesn't allow this.", "permission_denied", 403)
    with db_transaction.atomic():
        payment = (
            Payment.objects.select_for_update(of=("self",))
            .select_related("transfer")
            .filter(id=payment_id, organization_id=membership.organization_id)
            .first()
        )
        if payment is None:
            raise BusinessError("Payment not found.", "payment_not_found", 404)
        if payment.status != P.COMPLETED:
            raise BusinessError("Only a paid payment can be reversed.", "not_paid")
        if payment.external_payment_id:
            raise BusinessError(
                f"Money sent by M-Pesa or bank can't be taken back here. Ask {payment.recipient_name} to return it.",
                "not_reversible",
            )
        days = rules.platform().payroll_reversal_days
        if timezone.now() - payment.completed_at > timedelta(days=days):
            raise BusinessError(
                f"Payments can only be reversed within {days} days. Ask {payment.recipient_name} to send it back.",
                "reversal_window_passed",
            )
        source = BusinessEntry.Source.PAYROLL_REVERSAL if payment.pay_run_id else BusinessEntry.Source.REVERSAL

        def book(reversal):
            business_books.on_payment_reversal(
                reversal, payer=reversal.destination, payee=reversal.source, payer_role=books_role(payment),
                source=source,
            )  # fmt: skip

        reversal = reverse_transfer(
            transfer=payment.transfer, initiator=membership.user, reason=reason, books_role=BOOKED_BY_CALLER, book=book
        )
        payment.status, payment.reversal = P.REVERSED, reversal
        payment.reversed_by, payment.reversed_at, payment.reversal_reason = membership.user, timezone.now(), reason[:255]
        payment.save(update_fields=["status", "reversal", "reversed_by", "reversed_at", "reversal_reason", "updated_at"])
        record(
            "payroll.payslip_reversed" if payment.pay_run_id else "org.payment.reversed",
            actor=membership.user,
            organization_id=membership.organization_id,
            target=payment,
            metadata={**_payment_metadata(payment), "reason": reason, "reversal_reference": reversal.reference},
        )
    return payment


# --- Helpers ------------------------------------------------------------------------------------


def _recipient(organization, type_: str, worker_id, account_number: str):
    """(worker, wallet) a payment goes to: the worker's own wallet for the worker types, else the account."""
    if type_ in Payment.WORKER_TYPES:
        worker = (
            Worker.objects.select_related("wallet__owner")
            .filter(id=worker_id, organization=organization, status=Worker.Status.ACTIVE)
            .first()
            if worker_id
            else None
        )
        if worker is None:
            raise BusinessError("Choose one of the business's workers.", "worker_not_found", 404)
        return worker, worker.wallet
    if worker_id:
        raise BusinessError(
            "Only salaries, allowances, bonuses, commissions and other worker payments go to a worker.",
            "worker_not_allowed",
        )
    wallet = (
        Account.objects.select_related("owner", "organization")
        .filter(account_number=account_number, is_active=True, system_key__isnull=True)
        .first()
    )
    if wallet is None:
        raise BusinessError("No active account with that number.", "recipient_not_found", 404)
    return None, wallet


def _execute(payment: Payment, *, actor) -> None:
    """Sends a payment on its own. A business failure (insufficient funds...) marks it FAILED instead of raising."""
    try:
        send_payment(payment, actor=actor)
    except BusinessError as exc:
        payment.status, payment.failure_reason = P.FAILED, str(exc.detail)[:255]
        payment.save(update_fields=["status", "failure_reason", "updated_at"])


def _record_outcome(payment: Payment, *, actor) -> None:
    if payment.status == P.COMPLETED:
        record("org.payment.executed", actor=actor, organization_id=payment.organization_id, target=payment,
               metadata=_payment_metadata(payment))
    elif payment.status == P.FAILED:
        record("org.payment.failed", actor=actor, organization_id=payment.organization_id, target=payment,
               metadata={**_payment_metadata(payment), "reason": payment.failure_reason})


def _pending_approval(membership: Membership, payment_id) -> Payment:
    payment = (
        Payment.objects.select_for_update()
        .filter(id=payment_id, organization_id=membership.organization_id)
        .first()
    )
    if payment is None:
        raise BusinessError("Payment not found.", "payment_not_found", 404)
    if payment.status != P.PENDING_APPROVAL:
        raise BusinessError("This payment is no longer waiting for approval.", "not_pending")
    return payment


def _active_member(membership: Membership, target_id) -> Membership:
    target = (
        Membership.objects.select_related("user")
        .filter(id=target_id, organization_id=membership.organization_id, is_active=True)
        .first()
    )
    if target is None:
        raise BusinessError("Member not found.", "member_not_found", 404)
    return target


def _keep_an_owner(organization_id) -> None:
    """Call with the organization row locked, before demoting or removing an owner."""
    owners = Membership.objects.filter(organization_id=organization_id, role=Role.OWNER, is_active=True).count()
    if owners <= 1:
        raise BusinessError("A business needs at least one owner. Make someone else an owner first.", "last_owner")


def _payment_metadata(payment: Payment) -> dict:
    return {
        "type": payment.type,
        **({"beneficiary": str(payment.beneficiary_id)} if payment.beneficiary_id else {}),
        "amount": str(payment.amount),
        "currency": payment.source_account.currency,
        "from": payment.source_account.account_number,
        "to": payment.destination_account_number,
        "recipient": payment.recipient_name,
        "reference": payment.reference,
    }


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _send_invitation(organization, inviter, email: str, role: str, link: str) -> None:
    days = rules.platform().invitation_expiry_days
    send_mail(
        subject=f"You're invited to {organization.name} on FluxPay",
        message=(
            f"{inviter.full_name} invited you to join {organization.name} on FluxPay as {role.lower()}.\n\n"
            f"Open this link to accept it in the FluxPay app, signed in as {email} (it expires in {days} days):\n{link}\n"
        ),
        from_email=None,
        recipient_list=[email],
    )

