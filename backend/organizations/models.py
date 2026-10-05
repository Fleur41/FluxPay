import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower


class Organization(models.Model):
    """A business customer. Its wallets are banking.Account rows with `organization` set."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    registration_number = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    # Payments up to this amount run straight away; larger ones wait for a second person to approve.
    # 0 means every payment needs approval.
    approval_threshold = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))]
    )
    # Workers who enter or scan this code ask to join; someone approves each one. Empty: switched off.
    worker_join_code = models.CharField(max_length=12, unique=True, null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        ADMIN = "ADMIN", "Admin"
        FINANCE = "FINANCE", "Finance"
        VIEWER = "VIEWER", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices)
    is_active = models.BooleanField(default=True)  # removing someone deactivates; history stays
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [models.UniqueConstraint(fields=("organization", "user"), name="unique_membership")]

    def __str__(self) -> str:
        return f"{self.user} - {self.role} at {self.organization}"


class Invitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=Membership.Role.choices)
    # Only a SHA-256 of the token is stored; the token itself is only ever in the invite email.
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.email} -> {self.organization} ({self.role})"


class Beneficiary(models.Model):
    """Someone other than its own workers that a business pays: a supplier, a contractor, the landlord...

    They don't need a FluxPay account: the payout details say where their money goes. Changing those details
    unverifies them, and nothing is paid to the beneficiary until an approver has checked the new ones
    (organizations.beneficiaries.verify), so a changed bank account can't quietly redirect payments.
    Never deleted: a beneficiary the business stops paying is archived, and past payments still point at it.
    """

    class Kind(models.TextChoices):
        SUPPLIER = "SUPPLIER", "Supplier"
        VENDOR = "VENDOR", "Vendor"
        CONTRACTOR = "CONTRACTOR", "Contractor"
        LANDLORD = "LANDLORD", "Landlord"
        SERVICE_PROVIDER = "SERVICE_PROVIDER", "Service provider"
        UTILITY = "UTILITY", "Utility"
        OWN_ACCOUNT = "OWN_ACCOUNT", "The business's own account"  # where its withdrawals go
        OTHER = "OTHER", "Other"

    class Method(models.TextChoices):
        FLUXPAY = "FLUXPAY", "FluxPay account"
        MPESA_MOBILE = "MPESA_MOBILE", "M-Pesa phone number"
        MPESA_PAYBILL = "MPESA_PAYBILL", "M-Pesa paybill"
        MPESA_TILL = "MPESA_TILL", "M-Pesa till (Buy Goods)"
        BANK = "BANK", "Bank transfer"

    # Where the money goes. Changing any of these needs the beneficiary verified again.
    PAYOUT_FIELDS = (
        "method", "account_number", "mpesa_phone", "paybill_number", "paybill_account", "till_number",
        "bank_name", "bank_branch", "bank_account_name", "bank_account_number", "bank_swift_code",
    )  # fmt: skip

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="beneficiaries")
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    # Where its payments are filed in the business's books (accounting.business.CHART); empty = from the kind.
    books_category = models.CharField(max_length=20, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    notes = models.CharField(max_length=255, blank=True)

    method = models.CharField(max_length=16, choices=Method.choices)
    account_number = models.CharField(max_length=10, blank=True)  # FluxPay
    mpesa_phone = models.CharField(max_length=16, blank=True)  # E.164, +2547... or +2541...
    paybill_number = models.CharField(max_length=7, blank=True)
    paybill_account = models.CharField(max_length=20, blank=True)  # the account number at that paybill
    till_number = models.CharField(max_length=7, blank=True)
    bank_name = models.CharField(max_length=80, blank=True)
    bank_branch = models.CharField(max_length=80, blank=True)
    bank_account_name = models.CharField(max_length=150, blank=True)
    bank_account_number = models.CharField(max_length=34, blank=True)
    bank_swift_code = models.CharField(max_length=11, blank=True)

    details_changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    details_changed_at = models.DateTimeField()
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "beneficiaries"
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "organization", condition=models.Q(is_active=True), name="unique_active_beneficiary_name"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.organization})"

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None

    def payout_details(self) -> dict:
        """The payout details as they are now; a payment keeps a copy to prove where it was sent."""
        return {field: getattr(self, field) for field in self.PAYOUT_FIELDS if getattr(self, field)}


class Payment(models.Model):
    """Money a business pays out of its cashbook: to one of its workers (salary, allowance...) or to anyone
    else with a FluxPay wallet (a supplier, a contractor...).

    Every business payment is one of these, whether made on its own or as one line of a pay run
    (payroll.PayRun, which calls them payslips). The payment, the money movement (banking.Transfer) and the
    cashbook line all carry the same reference. Once paid it is never edited or deleted: a mistake is fixed
    by reversing it. Above the business's approval threshold, someone else must approve it first.
    """

    class Type(models.TextChoices):
        SALARY = "SALARY", "Salary"
        ALLOWANCE = "ALLOWANCE", "Allowance"
        BONUS = "BONUS", "Bonus"
        COMMISSION = "COMMISSION", "Commission"
        OTHER_WORKER = "OTHER_WORKER", "Other worker payment"
        SUPPLIER = "SUPPLIER", "Supplier payment"
        VENDOR = "VENDOR", "Vendor payment"
        CONTRACTOR = "CONTRACTOR", "Contractor payment"
        EXPENSE = "EXPENSE", "Business expense"
        WITHDRAWAL = "WITHDRAWAL", "Withdrawal"  # the owners taking money out of the business
        OTHER = "OTHER", "Other payment"

    WORKER_TYPES = (Type.SALARY, Type.ALLOWANCE, Type.BONUS, Type.COMMISSION, Type.OTHER_WORKER)

    class Status(models.TextChoices):
        PENDING_APPROVAL = "PENDING_APPROVAL", "Waiting for approval"
        PENDING = "PENDING", "Not paid yet"
        # The money has left the cashbook but M-Pesa or the bank hasn't confirmed it reached the recipient.
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Paid"
        FAILED = "FAILED", "Failed"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"
        REVERSED = "REVERSED", "Reversed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="payments")
    # The business's cashbook (its one wallet).
    source_account = models.ForeignKey("banking.Account", on_delete=models.PROTECT, related_name="+")
    type = models.CharField(max_length=12, choices=Type.choices)
    # Set for payments to a worker; required for the worker types.
    worker = models.ForeignKey(
        "payroll.Worker", on_delete=models.PROTECT, null=True, blank=True, related_name="payments"
    )
    # Set for payments to a saved beneficiary (a supplier, the landlord...), with their payout details then.
    beneficiary = models.ForeignKey(
        Beneficiary, on_delete=models.PROTECT, null=True, blank=True, related_name="payments"
    )
    beneficiary_details = models.JSONField(default=dict, blank=True)
    # Set when the payment is one line of a pay run.
    pay_run = models.ForeignKey(
        "payroll.PayRun", on_delete=models.PROTECT, null=True, blank=True, related_name="payslips"
    )
    destination_account_number = models.CharField(max_length=10, blank=True)  # FluxPay recipients only
    recipient_name = models.CharField(max_length=150)  # as it was when the payment was made
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    note = models.CharField(max_length=140, blank=True)
    # What the payment is for in the business's own books (accounting.business.CHART); empty = from its type.
    books_category = models.CharField(max_length=20, blank=True)
    reference = models.CharField(max_length=24, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True)
    transfer = models.OneToOneField(
        "banking.Transfer", on_delete=models.PROTECT, null=True, blank=True, related_name="payment"
    )
    # Set instead of `transfer` when the money went out by M-Pesa or bank (a beneficiary without FluxPay).
    external_payment = models.OneToOneField(
        "payments.ExternalPayment", on_delete=models.PROTECT, null=True, blank=True, related_name="business_payment"
    )
    failure_reason = models.CharField(max_length=255, blank=True)
    reversal = models.OneToOneField(
        "banking.Transfer", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_payment"
    )
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("organization", "-created_at"))]
        constraints = [
            models.UniqueConstraint(fields=("created_by", "idempotency_key"), name="unique_business_payment_idempotency"),
            models.UniqueConstraint(
                fields=("pay_run", "worker", "type"),
                condition=models.Q(pay_run__isnull=False),
                name="unique_pay_run_line",
            ),
            models.CheckConstraint(
                condition=~models.Q(type__in=["SALARY", "ALLOWANCE", "BONUS", "COMMISSION", "OTHER_WORKER"])
                | models.Q(worker__isnull=False),
                name="worker_payment_has_worker",
            ),
            models.CheckConstraint(
                condition=models.Q(worker__isnull=True) | models.Q(beneficiary__isnull=True),
                name="payment_to_worker_or_beneficiary",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_type_display()} {self.amount} to {self.recipient_name} ({self.status})"
