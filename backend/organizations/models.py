import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


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
        OTHER = "OTHER", "Other payment"

    WORKER_TYPES = (Type.SALARY, Type.ALLOWANCE, Type.BONUS, Type.COMMISSION, Type.OTHER_WORKER)

    class Status(models.TextChoices):
        PENDING_APPROVAL = "PENDING_APPROVAL", "Waiting for approval"
        PENDING = "PENDING", "Not paid yet"
        # The money has left the cashbook but hasn't reached the recipient yet (external rails).
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
    # Set when the payment is one line of a pay run.
    pay_run = models.ForeignKey(
        "payroll.PayRun", on_delete=models.PROTECT, null=True, blank=True, related_name="payslips"
    )
    destination_account_number = models.CharField(max_length=10)
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
        ]

    def __str__(self) -> str:
        return f"{self.get_type_display()} {self.amount} to {self.recipient_name} ({self.status})"
