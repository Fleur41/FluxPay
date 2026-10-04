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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="workers")
    wallet = models.ForeignKey("banking.Account", on_delete=models.PROTECT, related_name="employments")
    employee_number = models.CharField(max_length=30, blank=True)
    job_title = models.CharField(max_length=80, blank=True)
    salary = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0.01"))])
    is_active = models.BooleanField(default=True)  # leaving deactivates; past payslips stay
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("wallet__owner__full_name",)
        constraints = [models.UniqueConstraint(fields=("organization", "wallet"), name="unique_worker_wallet")]

    def __str__(self) -> str:
        return f"{self.name} at {self.organization}"

    @property
    def name(self) -> str:
        return self.wallet.owner.full_name


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
