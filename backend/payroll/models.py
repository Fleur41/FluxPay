"""Businesses paying their workers: a register of workers, and pay runs that pay many of them at once.

Workers are FluxPay users; their pay lands in their personal wallet. A pay run is one batch (e.g.
"October 2026 salaries") of business payments (organizations.Payment, `run.payslips`), one per worker and
type; above the business's approval threshold a second person must approve it. A payment made in error can
be taken back while the worker still holds the money.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

MONEY = {"max_digits": 14, "decimal_places": 2}


class Worker(models.Model):
    """Someone a business pays through FluxPay. They join only by invitation or with the business's approval:

        INVITED             the business invited them (by phone, email or FluxPay account); waiting for them to accept
        PENDING_ACTIVATION  they asked to join with the business's join code (or QR); waiting for the business
        ACTIVE              paid into their own FluxPay wallet
        SUSPENDED           kept on the register but can't be paid until reactivated
        DEACTIVATED         left, removed, or the invitation or request was cancelled; their pay history stays

    The worker's FluxPay account is their own: the business never sets or sees their password, and leaving
    a business doesn't close it.
    """

    class Status(models.TextChoices):
        INVITED = "INVITED", "Invited"
        PENDING_ACTIVATION = "PENDING_ACTIVATION", "Waiting for approval"
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        DEACTIVATED = "DEACTIVATED", "Deactivated"

    OPEN = (Status.INVITED, Status.PENDING_ACTIVATION, Status.ACTIVE, Status.SUSPENDED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="workers")
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    # Set once we know who the worker is: when invited by their FluxPay account, or when they accept or ask.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="employments"
    )
    # Their personal wallet that pay goes to; set when they become active.
    wallet = models.ForeignKey(
        "banking.Account", on_delete=models.PROTECT, null=True, blank=True, related_name="employments"
    )
    full_name = models.CharField(max_length=150)  # as the business entered it, until they join
    phone_number = models.CharField(max_length=16, blank=True)  # E.164; where the invitation was sent
    email = models.EmailField(blank=True)
    employee_number = models.CharField(max_length=30, blank=True)
    job_title = models.CharField(max_length=80, blank=True)
    # Empty only on a join request, until the business approves it.
    salary = models.DecimalField(**MONEY, null=True, blank=True, validators=[MinValueValidator(Decimal("0.01"))])
    # Only a SHA-256 of the invitation code is kept; the code itself is only in the SMS or email.
    invite_code_hash = models.CharField(max_length=64, blank=True, db_index=True)
    invite_expires_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    status_note = models.CharField(max_length=255, blank=True)  # why it was suspended, declined or removed
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("full_name",)
        constraints = [
            # Records of workers who left stay as history; a returning worker gets a new one.
            models.UniqueConstraint(
                fields=("organization", "wallet"),
                condition=models.Q(wallet__isnull=False) & ~models.Q(status="DEACTIVATED"),
                name="unique_worker_wallet",
            ),
            models.UniqueConstraint(
                fields=("organization", "user"),
                condition=models.Q(user__isnull=False) & ~models.Q(status="DEACTIVATED"),
                name="one_open_worker_record_per_user",
            ),
            models.UniqueConstraint(
                fields=("organization", "phone_number"),
                condition=models.Q(status="INVITED") & ~models.Q(phone_number=""),
                name="one_pending_invitation_per_phone",
            ),
            models.CheckConstraint(
                condition=~models.Q(status__in=["ACTIVE", "SUSPENDED"])
                | (models.Q(wallet__isnull=False) & models.Q(salary__isnull=False)),
                name="working_worker_has_wallet_and_salary",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} at {self.organization}"

    @property
    def name(self) -> str:
        return self.wallet.owner.full_name if self.wallet_id else self.full_name

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class PayRun(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Waiting for approval"
        PAID = "PAID", "Paid"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="pay_runs")
    source_account = models.ForeignKey("banking.Account", on_delete=models.PROTECT, related_name="+")
    title = models.CharField(max_length=80)
    pay_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    # Runs paid before each payslip got its own cashbook line were booked as one line for the whole run.
    book_entry = models.OneToOneField(
        "accounting.BusinessEntry", on_delete=models.PROTECT, null=True, blank=True, related_name="pay_run"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.title} ({self.organization})"
