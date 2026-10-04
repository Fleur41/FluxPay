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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="accounts")
    # Set for business wallets. Members reach them through organizations.*, never the personal endpoints;
    # `owner` is then just the member who opened the wallet.
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, null=True, blank=True, related_name="accounts"
    )
    account_number = models.CharField(max_length=10, unique=True, default=generate_account_number, editable=False)
    name = models.CharField(max_length=60, default="Main Wallet")
    # A platform_settings.Currency code; validated against the enabled currencies when a wallet is opened.
    currency = models.CharField(max_length=3)
    balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))]
    )
    is_active = models.BooleanField(default=True)
    # Set only on FluxPay's own clearing accounts (e.g. "clearing:PAYPAL:USD"); never on customer wallets.
    system_key = models.CharField(max_length=40, unique=True, null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            # Clearing accounts mirror money held at a provider, so they go negative as deposits come in.
            models.CheckConstraint(
                condition=models.Q(balance__gte=0) | models.Q(system_key__isnull=False),
                name="account_balance_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.account_number} ({self.currency}) - {self.owner}"

    @property
    def is_system(self) -> bool:
        return self.system_key is not None


class Transaction(models.Model):
    """One ledger line on one account. A transfer produces two: a DEBIT and a CREDIT.

    External payments post their two lines against a clearing account and share the payment's reference.
    """

    class Type(models.TextChoices):
        CREDIT = "CREDIT", "Credit"
        DEBIT = "DEBIT", "Debit"

    class Category(models.TextChoices):
        TRANSFER_IN = "TRANSFER_IN", "Transfer received"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer sent"
        BONUS = "BONUS", "Bonus"
        DEPOSIT = "DEPOSIT", "Deposit"
        WITHDRAWAL = "WITHDRAWAL", "Withdrawal"
        WITHDRAWAL_REVERSAL = "WITHDRAWAL_REVERSAL", "Withdrawal returned"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment by FluxPay"

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
    # Set when this transfer took a wrong payment back (e.g. a business pulling back a salary paid in error).
    reverses = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("initiated_by", "idempotency_key"), name="unique_transfer_idempotency"),
        ]


class ManualAdjustment(models.Model):
    """Money staff credited to a wallet from a bank receipt (top-up), returned to that receipt (correction),
    or paid out of the wallet in cash from the bank (payout), with the reason.

    Posted by banking.services.post_adjustment, which also books it in the general ledger. Never edited
    or deleted: a mistake is fixed with an opposite adjustment.
    """

    class Kind(models.TextChoices):
        CREDIT = "CREDIT", "Top-up (credit the wallet from a bank receipt)"
        DEBIT = "DEBIT", "Correction (return money to the bank receipt)"
        PAYOUT = "PAYOUT", "Cash withdrawal paid from the bank"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="adjustments")
    # The receipt the money came from (top-ups and corrections) or the payment that paid it out (payouts).
    # Empty only on adjustments made before the cashbook existed.
    cashbook_entry = models.ForeignKey(
        "accounting.CashbookEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="adjustments",
        verbose_name="bank receipt",
    )
    kind = models.CharField(max_length=6, choices=Kind.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    reason = models.CharField(
        max_length=255, help_text='Why, for the audit trail, e.g. "Cash deposited at the Nairobi office, receipt 1042".'
    )
    reference = models.CharField(max_length=24, unique=True)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        permissions = [("post_adjustment", "Can top up or correct customer wallets")]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.amount} on {self.account.account_number} ({self.reference})"
