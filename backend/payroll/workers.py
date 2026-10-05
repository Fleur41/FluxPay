"""How someone becomes, stays and stops being a business's worker (payroll.models.Worker, its statuses).

Joining always needs both sides: the business invites and the worker accepts, or the worker asks (with the
business's join code, typed or scanned as a QR code) and the business approves. A business can never be
found by its name, and a worker is never added without saying yes.

Invitation codes are 10 characters (about 50 bits), sent by SMS and email; only their SHA-256 is stored, they
expire, and entering them is rate-limited. Owners, admins and finance manage workers (Perm.MANAGE_WORKERS);
owners and admins approve join requests and run the join code (Perm.APPROVE_WORKER). Every change is audited.
"""

import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.utils import timezone

from audit.services import record
from banking.models import Account
from banking.services import open_wallet
from fluxpay.exceptions import BusinessError
from notifications.sms import get_sms_backend, normalize_phone
from organizations.models import Membership, Organization
from organizations.roles import Perm, Role, has_perm
from organizations.services import cashbook
from platform_settings import services as rules

from .models import Worker

W = Worker.Status
# Crockford's base 32: no I, L, O or U, so codes survive being read out or typed from an SMS.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 10


# --- Codes --------------------------------------------------------------------------------------


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(raw: str) -> str:
    """What the worker typed: any case, with or without the dash, O for 0 and I or L for 1."""
    cleaned = "".join(ch for ch in (raw or "").upper() if ch.isalnum())
    return cleaned.translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))


def display_code(code: str) -> str:
    return f"{code[:5]}-{code[5:]}"


def _hash(code: str) -> str:
    return hashlib.sha256(normalize_code(code).encode()).hexdigest()


# --- The business's side -----------------------------------------------------------------------


def _require(membership, perm: Perm) -> None:
    if not has_perm(membership.role, perm):
        raise BusinessError("Your role doesn't allow this.", "permission_denied", 403)


def salary(value) -> Decimal:
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise BusinessError("Enter the salary as a number, e.g. 25000.", "invalid_salary") from None
    if amount <= 0:
        raise BusinessError("The salary must be more than zero.", "invalid_salary")
    return amount.quantize(Decimal("0.01"))


def invite(*, membership, salary_amount, full_name="", phone_number="", email="", account_number="",
           employee_number="", job_title="", audit=True) -> tuple[Worker, str]:  # fmt: skip
    """Invites someone to be paid by this business: by phone (and email), or by their FluxPay account number.

    They get a code by SMS and email; they become a worker only once they accept it in the app.
    Returns (worker, code); the code is never stored.
    """
    _require(membership, Perm.MANAGE_WORKERS)
    organization = membership.organization
    currency = cashbook(organization).currency
    user = None
    if account_number:
        wallet = Account.objects.select_related("owner").filter(
            account_number=account_number.strip(), organization__isnull=True, system_key__isnull=True, is_active=True
        ).first()
        if wallet is None or not wallet.owner.is_active:
            raise BusinessError("No FluxPay personal account with that number.", "worker_not_found", 404)
        if wallet.currency != currency:
            raise BusinessError(f"That account is in {wallet.currency}; this business pays {currency}.", "currency_mismatch")
        user = wallet.owner
        full_name = user.full_name
        phone_number = phone_number or user.phone_number
        email = email or user.email
    phone = normalize_phone(phone_number) if phone_number else ""
    if phone_number and not phone:
        raise BusinessError("Enter a valid phone number, e.g. 0712 345 678.", "invalid_phone")
    if not phone and not email:
        raise BusinessError("Give the worker's phone number (or their FluxPay account number).", "contact_required")
    if user and Worker.objects.filter(organization=organization, user=user, status__in=Worker.OPEN).exists():
        raise BusinessError(f"{user.full_name} already works here or has a pending invitation.", "already_worker")

    code = new_code()
    try:
        with db_transaction.atomic():
            worker = Worker.objects.create(
                organization=organization, status=W.INVITED, user=user, full_name=(full_name or phone).strip()[:150],
                phone_number=phone or "", email=(email or "").strip().lower(), salary=salary(salary_amount),
                employee_number=employee_number.strip()[:30], job_title=job_title.strip()[:80],
                invite_code_hash=_hash(code), invite_expires_at=_expiry(), added_by=membership.user,
            )  # fmt: skip
            if audit:
                _audit("payroll.worker_invited", worker, actor=membership.user,
                       phone=worker.phone_number, email=worker.email)  # fmt: skip
            db_transaction.on_commit(lambda: _send_invitation(worker, code), robust=True)
    except IntegrityError:
        raise BusinessError("That phone number already has a pending invitation. Resend it instead.", "already_invited") from None
    return worker, code


def resend_invitation(*, membership, worker_id) -> tuple[Worker, str]:
    """A new code (the old one stops working) and a new expiry date."""
    _require(membership, Perm.MANAGE_WORKERS)
    code = new_code()
    with db_transaction.atomic():
        worker = get(membership, worker_id, lock=True)
        if worker.status != W.INVITED:
            raise BusinessError("Only a pending invitation can be sent again.", "not_invited")
        worker.invite_code_hash, worker.invite_expires_at = _hash(code), _expiry()
        worker.save(update_fields=["invite_code_hash", "invite_expires_at", "updated_at"])
        _audit("payroll.worker_invitation_resent", worker, actor=membership.user)
        db_transaction.on_commit(lambda: _send_invitation(worker, code), robust=True)
    return worker, code


def approve(*, membership, worker_id, salary_amount, job_title="", employee_number="") -> Worker:
    """Accepts a worker who asked to join, with their pay. Their pay goes to their own wallet."""
    _require(membership, Perm.APPROVE_WORKER)
    with db_transaction.atomic():
        worker = get(membership, worker_id, lock=True)
        if worker.status != W.PENDING_ACTIVATION:
            raise BusinessError("This worker isn't waiting for approval.", "not_pending")
        worker.salary = salary(salary_amount)
        worker.job_title = job_title.strip()[:80] or worker.job_title
        worker.employee_number = employee_number.strip()[:30] or worker.employee_number
        _activate(worker)
        _audit("payroll.worker_approved", worker, actor=membership.user, salary=str(worker.salary))
    return worker


def decline(*, membership, worker_id, reason: str = "") -> Worker:
    _require(membership, Perm.APPROVE_WORKER)
    with db_transaction.atomic():
        worker = get(membership, worker_id, lock=True)
        if worker.status != W.PENDING_ACTIVATION:
            raise BusinessError("This worker isn't waiting for approval.", "not_pending")
        _set_status(worker, W.DEACTIVATED, reason or "Join request declined")
        _audit("payroll.worker_declined", worker, actor=membership.user, reason=worker.status_note)
    return worker


def suspend(*, membership, worker_id, reason: str) -> Worker:
    """Keeps the worker on the register, but nobody can pay them until they are reactivated."""
    _require(membership, Perm.MANAGE_WORKERS)
    if len((reason or "").strip()) < 5:
        raise BusinessError("Say why the worker is suspended.", "reason_required")
    with db_transaction.atomic():
        worker = get(membership, worker_id, lock=True)
        if worker.status != W.ACTIVE:
            raise BusinessError("Only an active worker can be suspended.", "not_active")
        _set_status(worker, W.SUSPENDED, reason.strip())
        _audit("payroll.worker_suspended", worker, actor=membership.user, reason=worker.status_note)
    return worker


def reactivate(*, membership, worker_id) -> Worker:
    _require(membership, Perm.MANAGE_WORKERS)
    with db_transaction.atomic():
        worker = get(membership, worker_id, lock=True)
        if worker.status != W.SUSPENDED:
            raise BusinessError(
                "Only a suspended worker can be reactivated. Invite someone who left again.", "not_suspended"
            )
        _set_status(worker, W.ACTIVE, "")
        _audit("payroll.worker_reactivated", worker, actor=membership.user)
    return worker


def deactivate(*, membership, worker_id, reason: str = "") -> Worker:
    """Removes a worker, or cancels an invitation or join request. Their pay history stays; their FluxPay
    account is untouched."""
    _require(membership, Perm.MANAGE_WORKERS)
    with db_transaction.atomic():
        worker = get(membership, worker_id, lock=True)
        if worker.status == W.DEACTIVATED:
            return worker
        _set_status(worker, W.DEACTIVATED, reason or "Removed by the business")
        _audit("payroll.worker_removed", worker, actor=membership.user, reason=worker.status_note)
    return worker


def update(*, membership, worker_id, **changes) -> Worker:
    """Pay details. `is_active` is kept for older apps: False removes, True reactivates a suspended worker."""
    _require(membership, Perm.MANAGE_WORKERS)
    if "is_active" in changes:
        active, status = changes.pop("is_active"), get(membership, worker_id).status
        if active is False:
            deactivate(membership=membership, worker_id=worker_id)
        elif status == W.SUSPENDED:
            reactivate(membership=membership, worker_id=worker_id)
        elif status == W.DEACTIVATED:
            raise BusinessError("This worker left. Invite them again instead.", "not_suspended")
    with db_transaction.atomic():
        worker = get(membership, worker_id, lock=True)
        if "salary" in changes:
            changes["salary"] = salary(changes["salary"])
        before = {}
        for field in ("salary", "job_title", "employee_number"):
            if field in changes and getattr(worker, field) != changes[field]:
                before[field] = str(getattr(worker, field))
                setattr(worker, field, changes[field])
        if before:
            worker.save(update_fields=[*before, "updated_at"])
            _audit("payroll.worker_changed", worker, actor=membership.user, before=before,
                   after={f: str(getattr(worker, f)) for f in before})  # fmt: skip
    return worker


def import_workers(*, membership, rows: list[dict]) -> dict:
    """Invites many workers at once (e.g. from a spreadsheet). Good rows are invited; bad rows are reported back.

    Each row: account_number or phone_number (and full_name), salary, and optionally email, employee_number
    and job_title.
    """
    _require(membership, Perm.MANAGE_WORKERS)
    invited, errors = 0, []
    with db_transaction.atomic():
        for number, row in enumerate(rows, start=1):
            try:
                with db_transaction.atomic():
                    invite(
                        membership=membership, audit=False, salary_amount=row.get("salary"),
                        **{f: str(row.get(f) or "") for f in ("full_name", "phone_number", "email", "account_number",
                                                              "employee_number", "job_title")},
                    )  # fmt: skip
            except BusinessError as exc:
                errors.append({"row": number, "error": str(exc.detail)})
                continue
            invited += 1
        record(
            "payroll.workers_imported", actor=membership.user, organization_id=membership.organization_id,
            target=membership.organization, metadata={"invited": invited, "errors": len(errors)},
        )  # fmt: skip
    return {"created": invited, "updated": 0, "errors": errors}


def set_join_code(*, membership, enabled: bool) -> Organization:
    """Switches the business's join code on with a new code (the old one stops working), or off."""
    _require(membership, Perm.APPROVE_WORKER)
    with db_transaction.atomic():
        organization = Organization.objects.select_for_update().get(pk=membership.organization_id)
        organization.worker_join_code = new_code() if enabled else None
        organization.save(update_fields=["worker_join_code", "updated_at"])
        record(
            "payroll.join_code_changed" if enabled else "payroll.join_code_disabled", actor=membership.user,
            organization_id=organization.id, target=organization,
        )  # fmt: skip
    return organization


# --- The worker's side ---------------------------------------------------------------------------


def preview_invitation(code: str) -> Worker:
    """The invitation a code belongs to, so the app can show who it's from before the worker accepts."""
    worker = Worker.objects.select_related("organization").filter(invite_code_hash=_hash(code)).first()
    _check_invitation(worker)
    return worker


def accept_invitation(*, user, code: str) -> Worker:
    """The worker says yes: they become active, paid into their own wallet in the business's currency."""
    with db_transaction.atomic():
        worker = (
            Worker.objects.select_for_update().select_related("organization")
            .filter(invite_code_hash=_hash(code)).first()
        )  # fmt: skip
        _check_invitation(worker)
        if worker.user_id and worker.user_id != user.id:
            raise BusinessError("This invitation was sent to a different FluxPay account.", "invitation_user_mismatch", 403)
        _close_join_request(worker.organization_id, user)
        worker.user = user
        try:
            with db_transaction.atomic():
                _activate(worker)
        except IntegrityError:
            raise BusinessError(f"You already work for {worker.organization.name}.", "already_worker") from None
        _audit("payroll.worker_joined", worker, actor=user)
    return worker


def request_to_join(*, user, join_code: str) -> Worker:
    """The worker asks to join a business by its join code; the business approves or declines."""
    code = normalize_code(join_code)
    organization = Organization.objects.filter(worker_join_code=code).first() if code else None
    if organization is None or organization.status != Organization.Status.ACTIVE:
        raise BusinessError("That join code isn't valid. Ask the business for its current code.", "join_code_invalid", 404)
    existing = Worker.objects.filter(organization=organization, user=user, status__in=Worker.OPEN).first()
    if existing:
        raise BusinessError(
            {W.INVITED: "You already have an invitation from this business: open the link we sent you.",
             W.PENDING_ACTIVATION: "You've already asked to join; the business hasn't answered yet."}.get(
                existing.status, f"You already work for {organization.name}."),
            "already_worker",
        )  # fmt: skip
    try:
        with db_transaction.atomic():
            worker = Worker.objects.create(
                organization=organization, status=W.PENDING_ACTIVATION, user=user, full_name=user.full_name,
                phone_number=normalize_phone(user.phone_number or "") or "", email=user.email, added_by=user,
            )  # fmt: skip
            _audit("payroll.worker_join_requested", worker, actor=user)
            db_transaction.on_commit(lambda: _tell_approvers(worker), robust=True)
    except IntegrityError:
        raise BusinessError(f"You already work for {organization.name}.", "already_worker") from None
    return worker


def leave(*, user, worker_id) -> Worker:
    """The worker stops working for a business (or turns down an invitation sent to their account)."""
    with db_transaction.atomic():
        worker = Worker.objects.select_for_update().filter(id=worker_id, user=user).first()
        if worker is None:
            raise BusinessError("Not found.", "worker_not_found", 404)
        if worker.status != W.DEACTIVATED:
            _set_status(worker, W.DEACTIVATED, "Left")
            _audit("payroll.worker_left", worker, actor=user)
    return worker


# --- Helpers ------------------------------------------------------------------------------------


def get(membership, worker_id, *, lock=False) -> Worker:
    workers = Worker.objects.select_related("wallet__owner", "organization").filter(
        organization_id=membership.organization_id
    )
    worker = (workers.select_for_update(of=("self",)) if lock else workers).filter(id=worker_id).first()
    if worker is None:
        raise BusinessError("Worker not found.", "worker_not_found", 404)
    return worker



def _expiry():
    return timezone.now() + timedelta(days=rules.platform().invitation_expiry_days)


def _check_invitation(worker) -> None:
    if worker is None or worker.status != W.INVITED or worker.invite_expires_at <= timezone.now():
        raise BusinessError("This invitation code is invalid or has expired. Ask the business to send it again.",
                            "invitation_invalid", 404)  # fmt: skip
    if worker.organization.status != Organization.Status.ACTIVE:
        raise BusinessError("This business is suspended.", "organization_suspended", 403)


def _activate(worker: Worker) -> None:
    """Links the worker's own wallet in the business's currency (opening one if they have none) and makes them
    ACTIVE. The row is locked by the caller."""
    currency = cashbook(worker.organization).currency
    user = worker.user
    wallet = Account.objects.filter(
        owner=user, currency=currency, organization__isnull=True, system_key__isnull=True, is_active=True
    ).order_by("created_at").first() or open_wallet(user, currency=currency)
    worker.wallet, worker.full_name = wallet, user.full_name
    worker.phone_number = worker.phone_number or normalize_phone(user.phone_number or "") or ""
    worker.status, worker.status_note, worker.activated_at = W.ACTIVE, "", timezone.now()
    worker.invite_code_hash, worker.invite_expires_at = "", None
    worker.save()


def _set_status(worker: Worker, status: str, note: str) -> None:
    worker.status, worker.status_note = status, note[:255]
    if status == W.DEACTIVATED:
        worker.invite_code_hash, worker.invite_expires_at = "", None
    worker.save(update_fields=["status", "status_note", "invite_code_hash", "invite_expires_at", "updated_at"])


def _close_join_request(organization_id, user) -> None:
    """A worker who asked to join and then accepted an invitation: the invitation wins."""
    Worker.objects.filter(organization_id=organization_id, user=user, status=W.PENDING_ACTIVATION).update(
        status=W.DEACTIVATED, status_note="Joined by invitation instead", updated_at=timezone.now()
    )


def _audit(action: str, worker: Worker, *, actor, **metadata) -> None:
    record(action, actor=actor, organization_id=worker.organization_id, target=worker,
           metadata={"name": worker.name, "status": worker.status, **metadata})  # fmt: skip


def _send_invitation(worker: Worker, code: str) -> None:
    business = worker.organization.name
    link = settings.WORKER_INVITE_LINK.format(code=code)
    days = rules.platform().invitation_expiry_days
    text = (f"{business} invited you to get paid through FluxPay. Open {link} or enter code {display_code(code)} "
            f"in the FluxPay app (I work for a business). Expires in {days} days.")  # fmt: skip
    if worker.phone_number:
        get_sms_backend().send(worker.phone_number, text)
    if worker.email:
        send_mail(
            subject=f"{business} invited you to get paid through FluxPay", from_email=None,
            recipient_list=[worker.email],
            message=f"Hello {worker.full_name},\n\n{text}\n\nYou'll create your own FluxPay login; "
                    f"{business} never sees your password.\n",
        )  # fmt: skip


def _tell_approvers(worker: Worker) -> None:
    emails = list(
        Membership.objects.filter(
            organization_id=worker.organization_id, is_active=True, role__in=[Role.OWNER, Role.ADMIN]
        ).values_list("user__email", flat=True)
    )
    if emails:
        send_mail(
            subject=f"{worker.full_name} asked to join {worker.organization.name} as a worker", from_email=None,
            recipient_list=emails,
            message=f"{worker.full_name} used your join code. Approve or decline them under Workers in the "
                    "FluxPay app. Nobody is added without your approval.\n",
        )  # fmt: skip
