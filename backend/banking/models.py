import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


def generate_account_number() -> str:
    """10-digit account number, never starting with 0."""
    return str(secrets.randbelow(9_000_000_000) + 1_000_000_000)


class Account(models.Model):
    class Currency(models.TextChoices):
        KES = "KES", "Kenyan Shilling"
        USD = "USD", "US Dollar"
        EUR = "EUR", "Euro"
        GBP = "GBP", "British Pound"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="accounts")
    account_number = models.CharField(max_length=10, unique=True, default=generate_account_number, editable=False)
    name = models.CharField(max_length=60, default="Main Wallet")
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.KES)
    balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))]
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(condition=models.Q(balance__gte=0), name="account_balance_non_negative"),
        ]

    def __str__(self) -> str:
        return f"{self.account_number} ({self.currency}) - {self.owner}"


class Transaction(models.Model):
    """One ledger line on one account. A transfer produces two: a DEBIT and a CREDIT."""

    class Type(models.TextChoices):
        CREDIT = "CREDIT", "Credit"
        DEBIT = "DEBIT", "Debit"

    class Category(models.TextChoices):
        TRANSFER_IN = "TRANSFER_IN", "Transfer received"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer sent"
        BONUS = "BONUS", "Bonus"
        DEPOSIT = "DEPOSIT", "Deposit"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transactions")
    type = models.CharField(max_length=6, choices=Type.choices)
    category = models.CharField(max_length=20, choices=Category.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.COMPLETED)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    counterparty_name = models.CharField(max_length=150, blank=True)
    counterparty_account = models.CharField(max_length=10, blank=True)
    description = models.CharField(max_length=140, blank=True)
    reference = models.CharField(max_length=24, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("account", "-created_at"))]

    def __str__(self) -> str:
        return f"{self.type} {self.amount} on {self.account.account_number}"


class Transfer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="transfers")
    source = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="outgoing_transfers")
    destination = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="incoming_transfers")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=140, blank=True)
    reference = models.CharField(max_length=24, unique=True)
    # Lets the app retry a request safely without sending money twice.
    idempotency_key = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("initiated_by", "idempotency_key"), name="unique_transfer_idempotency"),
        ]
