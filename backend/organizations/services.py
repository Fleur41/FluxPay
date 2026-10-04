"""Business accounts: organizations, members, invitations and approved payments.

Every action checks the caller's role (organizations.roles) and writes an audit event in the same
transaction. Lock order: organization row, then payment request row, then accounts, then audit.
"""
import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction as db_transaction
from django.utils import timezone
from rest_framework import status

from audit.services import record
from banking.models import Account
from banking.services import transfer_from_organization
from fluxpay.exceptions import BusinessError
from platform_settings import services as rules

from .models import Invitation, Membership, Organization, PaymentRequest
from .roles import Perm, Role, can_manage, has_perm

PR = PaymentRequest.Status


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


def create_payment_request(*, membership: Membership, source_account_id, destination_account_number: str,
                           amount: Decimal, note: str, idempotency_key: str) -> tuple[PaymentRequest, bool]:
    """Records a payment. Up to the approval threshold it is sent straight away; above it, it waits."""
    user, organization = membership.user, membership.organization
    existing = PaymentRequest.objects.filter(created_by=user, idempotency_key=idempotency_key).first()
    if existing:
        return existing, False
    source = Account.objects.filter(id=source_account_id, organization=organization, is_active=True).first()
    if source is None:
        raise BusinessError("Business wallet not found.", "account_not_found", 404)
    rules.check_amount(amount, source.currency)
    if not Account.objects.filter(
        account_number=destination_account_number, is_active=True, system_key__isnull=True
    ).exists():
        raise BusinessError("No active account with that number.", "recipient_not_found", 404)

    try:
        with db_transaction.atomic():
            request = PaymentRequest.objects.create(
                organization=organization,
                source_account=source,
                destination_account_number=destination_account_number,
                amount=amount,
                note=note,
                status=PR.PENDING_APPROVAL,
                created_by=user,
                idempotency_key=idempotency_key,
            )
            if amount <= organization.approval_threshold:
                _execute(request)  # locks accounts, so it runs before this transaction's first audit event
            record("org.payment.created", actor=user, organization_id=organization.id, target=request,
                   metadata=_payment_metadata(request))
            _record_outcome(request, actor=user)
    except IntegrityError:
        return PaymentRequest.objects.get(created_by=user, idempotency_key=idempotency_key), False
    return request, True


def approve_payment_request(*, membership: Membership, request_id, note: str = "") -> PaymentRequest:
    """A second person approves, and the payment is sent. The creator can never approve their own."""
    with db_transaction.atomic():
        request = _pending_request(membership, request_id)
        if request.created_by_id == membership.user_id:
            raise BusinessError("You can't approve a payment you created.", "self_approval", 403)
        request.decided_by, request.decided_at, request.decision_note = membership.user, timezone.now(), note[:255]
        request.save(update_fields=["decided_by", "decided_at", "decision_note", "updated_at"])
        _execute(request)
        record("org.payment.approved", actor=membership.user, organization_id=request.organization_id,
               target=request, metadata=_payment_metadata(request))
        _record_outcome(request, actor=membership.user)
    return request


def reject_payment_request(*, membership: Membership, request_id, note: str = "") -> PaymentRequest:
    with db_transaction.atomic():
        request = _pending_request(membership, request_id)
        request.status, request.decided_by, request.decided_at = PR.REJECTED, membership.user, timezone.now()
        request.decision_note = note[:255]
        request.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
        record("org.payment.rejected", actor=membership.user, organization_id=request.organization_id,
               target=request, metadata={**_payment_metadata(request), "note": request.decision_note})
    return request


def cancel_payment_request(*, membership: Membership, request_id) -> PaymentRequest:
    """The creator withdraws a payment that hasn't been decided yet."""
    with db_transaction.atomic():
        request = _pending_request(membership, request_id)
        if request.created_by_id != membership.user_id:
            raise BusinessError("Only the person who created this payment can cancel it.", "permission_denied", 403)
        request.status = PR.CANCELLED
        request.save(update_fields=["status", "updated_at"])
        record("org.payment.cancelled", actor=membership.user, organization_id=request.organization_id,
               target=request, metadata=_payment_metadata(request))
    return request


# --- Helpers ------------------------------------------------------------------------------------


def _execute(request: PaymentRequest) -> None:
    """Sends the money. A business failure (insufficient funds...) marks the request FAILED instead of raising.

    The transfer's idempotency key is derived from the request, so a request can only ever pay once.
    """
    try:
        transfer, _debit, _created = transfer_from_organization(
            initiator=request.created_by,
            organization=request.organization,
            source_id=request.source_account_id,
            destination_number=request.destination_account_number,
            amount=request.amount,
            note=request.note,
            idempotency_key=f"payment-request-{request.id}",
        )
    except BusinessError as exc:
        request.status, request.failure_reason = PR.FAILED, str(exc.detail)[:255]
        request.save(update_fields=["status", "failure_reason", "updated_at"])
        return
    request.status, request.transfer = PR.EXECUTED, transfer
    request.save(update_fields=["status", "transfer", "updated_at"])


def _record_outcome(request: PaymentRequest, *, actor) -> None:
    if request.status == PR.EXECUTED:
        record("org.payment.executed", actor=actor, organization_id=request.organization_id, target=request,
               metadata={**_payment_metadata(request), "reference": request.transfer.reference})
    elif request.status == PR.FAILED:
        record("org.payment.failed", actor=actor, organization_id=request.organization_id, target=request,
               metadata={**_payment_metadata(request), "reason": request.failure_reason})


def _pending_request(membership: Membership, request_id) -> PaymentRequest:
    request = (
        PaymentRequest.objects.select_for_update()
        .filter(id=request_id, organization_id=membership.organization_id)
        .first()
    )
    if request is None:
        raise BusinessError("Payment not found.", "payment_request_not_found", 404)
    if request.status != PR.PENDING_APPROVAL:
        raise BusinessError("This payment is no longer waiting for approval.", "not_pending")
    return request


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


def _payment_metadata(request: PaymentRequest) -> dict:
    return {
        "amount": str(request.amount),
        "currency": request.source_account.currency,
        "from": request.source_account.account_number,
        "to": request.destination_account_number,
    }


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _send_invitation(organization, inviter, email: str, role: str, link: str) -> None:
    days = rules.platform().invitation_expiry_days
    send_mail(
        subject=f"You're invited to {organization.name} on FluxPay",
        message=(
            f"{inviter.full_name} invited you to join {organization.name} on FluxPay as {role.lower()}.\n\n"
            f"Open this link on your phone to accept (it expires in {days} days):\n{link}\n"
        ),
        from_email=None,
        recipient_list=[email],
    )

