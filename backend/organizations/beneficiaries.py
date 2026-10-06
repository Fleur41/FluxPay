"""A business's saved beneficiaries: suppliers, contractors, the landlord... and their payout details.

Owners, admins and finance manage them (Perm.MANAGE_BENEFICIARIES). Payout details are checked here, one
set per method. Whenever they change, the beneficiary is unverified until an owner or admin verifies the
new details, and that must be someone other than the person who entered them, unless the business has no
other approver. Payments only go to verified beneficiaries (organizations.services), so someone who can
edit a beneficiary can't redirect its payments to their own account without a second person noticing.
"""

import re

from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.utils import timezone

from audit.services import record
from banking.models import Account
from fluxpay.exceptions import BusinessError
from notifications.sms import normalize_phone

from .models import Beneficiary, Membership, Payment
from .roles import Perm, Role, has_perm

M = Beneficiary.Method
CONTACT_FIELDS = ("name", "kind", "books_category", "contact_phone", "contact_email", "notes")
# Each method's fields; the other payout fields are cleared.
METHOD_FIELDS = {
    M.FLUXPAY: ("account_number",),
    M.MPESA_MOBILE: ("mpesa_phone",),
    M.MPESA_PAYBILL: ("paybill_number", "paybill_account"),
    M.MPESA_TILL: ("till_number",),
    M.BANK: ("bank_name", "bank_branch", "bank_account_name", "bank_account_number", "bank_swift_code"),
}
# What paying each kind of beneficiary counts as, unless the payer says otherwise.
PAYMENT_TYPE = {
    Beneficiary.Kind.SUPPLIER: Payment.Type.SUPPLIER,
    Beneficiary.Kind.VENDOR: Payment.Type.VENDOR,
    Beneficiary.Kind.CONTRACTOR: Payment.Type.CONTRACTOR,
    Beneficiary.Kind.LANDLORD: Payment.Type.EXPENSE,
    Beneficiary.Kind.SERVICE_PROVIDER: Payment.Type.EXPENSE,
    Beneficiary.Kind.UTILITY: Payment.Type.EXPENSE,
    Beneficiary.Kind.OWN_ACCOUNT: Payment.Type.WITHDRAWAL,
    Beneficiary.Kind.OTHER: Payment.Type.OTHER,
}


def _require(membership: Membership, perm: Perm) -> None:
    if not has_perm(membership.role, perm):
        raise BusinessError("Your role doesn't allow this.", "permission_denied", 403)


def add(*, membership: Membership, name: str, kind: str, method: str, **fields) -> Beneficiary:
    _require(membership, Perm.MANAGE_BENEFICIARIES)
    organization = membership.organization
    contact = {f: (fields.get(f) or "").strip() for f in CONTACT_FIELDS if f not in ("name", "kind")}
    details = _clean_details(organization, method, fields)
    now = timezone.now()
    try:
        with db_transaction.atomic():
            beneficiary = Beneficiary.objects.create(
                organization=organization, name=_name(name), kind=kind, **contact, **details,
                details_changed_by=membership.user, details_changed_at=now, created_by=membership.user,
            )  # fmt: skip
            record(
                "org.beneficiary.added", actor=membership.user, organization_id=organization.id, target=beneficiary,
                metadata={"name": beneficiary.name, "kind": kind, "details": beneficiary.payout_details()},
            )  # fmt: skip
    except IntegrityError:
        raise BusinessError(f"You already have a beneficiary called {name.strip()}.", "duplicate_beneficiary") from None
    return beneficiary


def update(*, membership: Membership, beneficiary_id, **changes) -> Beneficiary:
    """Changes contact details freely; changing payout details unverifies the beneficiary."""
    _require(membership, Perm.MANAGE_BENEFICIARIES)
    try:
        with db_transaction.atomic():
            beneficiary = get(membership, beneficiary_id, lock=True)
            if not beneficiary.is_active:
                raise BusinessError("This beneficiary is archived.", "beneficiary_archived")
            before, after = {}, {}
            for field in CONTACT_FIELDS:
                if field in changes:
                    value = _name(changes[field]) if field == "name" else (changes[field] or "").strip()
                    if value != getattr(beneficiary, field):
                        before[field], after[field] = getattr(beneficiary, field), value
                        setattr(beneficiary, field, value)

            old_details = beneficiary.payout_details()
            if any(field in changes for field in Beneficiary.PAYOUT_FIELDS):
                method = changes.get("method") or beneficiary.method
                # Fields not sent keep their value, unless the method changed (then they must all be sent).
                current = {} if method != beneficiary.method else old_details
                details = _clean_details(beneficiary.organization, method, {**current, **changes})
                if {k: v for k, v in details.items() if v} != old_details:
                    for field, value in details.items():
                        setattr(beneficiary, field, value)
                    beneficiary.details_changed_by, beneficiary.details_changed_at = membership.user, timezone.now()
                    beneficiary.verified_by = beneficiary.verified_at = None
            new_details = beneficiary.payout_details()
            if not before and new_details == old_details:
                return beneficiary
            beneficiary.save()
            if new_details != old_details:
                record(
                    "org.beneficiary.details_changed", actor=membership.user,
                    organization_id=beneficiary.organization_id, target=beneficiary,
                    metadata={"name": beneficiary.name, "before": old_details, "after": new_details},
                )  # fmt: skip
            if before:
                record(
                    "org.beneficiary.changed", actor=membership.user, organization_id=beneficiary.organization_id,
                    target=beneficiary, metadata={"name": beneficiary.name, "before": before, "after": after},
                )  # fmt: skip
    except IntegrityError:
        raise BusinessError(f"You already have a beneficiary called {changes.get('name')}.", "duplicate_beneficiary") from None
    return beneficiary


def verify(*, membership: Membership, beneficiary_id) -> Beneficiary:
    """An owner or admin confirms the payout details are right (e.g. against the supplier's invoice)."""
    _require(membership, Perm.APPROVE_PAYMENT)
    with db_transaction.atomic():
        beneficiary = get(membership, beneficiary_id, lock=True)
        if not beneficiary.is_active:
            raise BusinessError("This beneficiary is archived.", "beneficiary_archived")
        if beneficiary.is_verified:
            raise BusinessError("These details are already verified.", "already_verified")
        if beneficiary.details_changed_by_id == membership.user_id and _other_approvers(membership):
            raise BusinessError(
                "You entered these payout details, so another owner or admin must verify them.", "self_verification", 403
            )
        beneficiary.verified_by, beneficiary.verified_at = membership.user, timezone.now()
        beneficiary.save(update_fields=["verified_by", "verified_at", "updated_at"])
        record(
            "org.beneficiary.verified", actor=membership.user, organization_id=beneficiary.organization_id,
            target=beneficiary, metadata={"name": beneficiary.name, "details": beneficiary.payout_details()},
        )  # fmt: skip
    return beneficiary


def archive(*, membership: Membership, beneficiary_id) -> Beneficiary:
    _require(membership, Perm.MANAGE_BENEFICIARIES)
    with db_transaction.atomic():
        beneficiary = get(membership, beneficiary_id, lock=True)
        if beneficiary.is_active:
            beneficiary.is_active = False
            beneficiary.save(update_fields=["is_active", "updated_at"])
            record("org.beneficiary.archived", actor=membership.user, organization_id=beneficiary.organization_id,
                   target=beneficiary, metadata={"name": beneficiary.name})  # fmt: skip
    return beneficiary


def payable(organization, beneficiary_id) -> Beneficiary:
    """A beneficiary that may be paid now: this business's, active and verified."""
    beneficiary = Beneficiary.objects.filter(id=beneficiary_id, organization=organization).first()
    if beneficiary is None:
        raise BusinessError("Beneficiary not found.", "beneficiary_not_found", 404)
    check_payable(beneficiary)
    return beneficiary


def check_payable(beneficiary: Beneficiary, details: dict | None = None) -> None:
    """Raises unless `beneficiary` can be paid; with `details`, also unless its payout details are still those."""
    if not beneficiary.is_active:
        raise BusinessError(f"{beneficiary.name} is archived.", "beneficiary_archived")
    if not beneficiary.is_verified:
        raise BusinessError(
            f"{beneficiary.name}'s payout details haven't been verified yet. An owner or admin must verify them first.",
            "beneficiary_unverified",
        )
    if details is not None and details != beneficiary.payout_details():
        raise BusinessError(
            f"{beneficiary.name}'s payout details changed after this payment was created. Create it again.",
            "beneficiary_changed",
        )


def mask(details: dict) -> dict:
    """Payout details for members who can't manage beneficiaries: account numbers show their last 4 digits."""
    hidden = ("account_number", "mpesa_phone", "paybill_account", "bank_account_number")
    return {k: ("•••• " + v[-4:] if k in hidden and v else v) for k, v in details.items()}


# --- Helpers ------------------------------------------------------------------------------------


def get(membership: Membership, beneficiary_id, *, lock=False) -> Beneficiary:
    beneficiaries = Beneficiary.objects.filter(organization_id=membership.organization_id)
    beneficiary = (beneficiaries.select_for_update() if lock else beneficiaries).filter(id=beneficiary_id).first()
    if beneficiary is None:
        raise BusinessError("Beneficiary not found.", "beneficiary_not_found", 404)
    return beneficiary


def _other_approvers(membership: Membership) -> bool:
    return (
        Membership.objects.filter(
            organization_id=membership.organization_id, is_active=True, role__in=[Role.OWNER, Role.ADMIN]
        )
        .exclude(user_id=membership.user_id)
        .exists()
    )


def _name(value) -> str:
    name = (value or "").strip()
    if not name:
        raise BusinessError("Give the beneficiary a name.", "name_required")
    return name[:150]


def _clean_details(organization, method: str, data: dict) -> dict:
    """Every payout field for `method`, checked and normalised; the other methods' fields blank."""
    if method not in METHOD_FIELDS:
        raise BusinessError("Choose how this beneficiary is paid.", "invalid_method")
    value = {f: re.sub(r"\s+", " ", str(data.get(f) or "")).strip() for f in METHOD_FIELDS[method]}
    details = {field: "" for field in Beneficiary.PAYOUT_FIELDS} | value | {"method": method}

    if method == M.FLUXPAY:
        number = value["account_number"]
        wallet = Account.objects.filter(account_number=number, is_active=True, system_key__isnull=True).first()
        if not re.fullmatch(r"\d{10}", number) or wallet is None:
            raise BusinessError("No active FluxPay account with that number.", "recipient_not_found")
        if wallet.organization_id == organization.id:
            raise BusinessError("That's this business's own cashbook.", "same_account")
    elif method == M.MPESA_MOBILE:
        phone = normalize_phone(value["mpesa_phone"])
        if not phone or not re.fullmatch(r"\+254[17]\d{8}", phone):
            raise BusinessError("Enter a Kenyan M-Pesa number, e.g. 0712 345 678.", "invalid_phone")
        details["mpesa_phone"] = phone
    elif method == M.MPESA_PAYBILL:
        if not re.fullmatch(r"\d{5,7}", value["paybill_number"]):
            raise BusinessError("A paybill number is 5 to 7 digits.", "invalid_paybill")
        if not re.fullmatch(r"[A-Za-z0-9 -]{1,20}", value["paybill_account"]):
            raise BusinessError(
                "Enter the account number at the paybill (up to 20 letters or digits).", "invalid_paybill_account"
            )
    elif method == M.MPESA_TILL:
        if not re.fullmatch(r"\d{5,7}", value["till_number"]):
            raise BusinessError("A till number is 5 to 7 digits.", "invalid_till")
    elif method == M.BANK:
        if not value["bank_name"] or not value["bank_account_name"]:
            raise BusinessError("Enter the bank and the name on the account.", "bank_details_required")
        number = value["bank_account_number"].replace(" ", "").replace("-", "")
        if not re.fullmatch(r"[A-Za-z0-9]{6,34}", number):
            raise BusinessError("Enter the bank account number (6 to 34 letters or digits).", "invalid_bank_account")
        swift = value["bank_swift_code"].upper()
        if swift and not re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?", swift):
            raise BusinessError("A SWIFT code is 8 or 11 letters and digits.", "invalid_swift")
        details["bank_account_number"], details["bank_swift_code"] = number.upper(), swift
    return details
