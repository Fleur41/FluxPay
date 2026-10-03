import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from banking.models import Account


class Rail(models.TextChoices):
    MPESA = "MPESA", "M-Pesa"
    PAYPAL = "PAYPAL", "PayPal"
    BANK = "BANK", "Bank transfer"
    FAKE = "FAKE", "Fake (tests and local dev)"


class ExternalPayment(models.Model):
    """Money moving between a FluxPay wallet and an outside provider.

    Deposits:     CREATED -> PENDING -> COMPLETED | FAILED | EXPIRED
                  (EXPIRED -> COMPLETED when the money arrives after we stopped waiting)
    Withdrawals:  HELD -> SUBMITTED -> COMPLETED | REVERSED
                  (created already HELD, with the money out of the wallet; a failure returns it -> REVERSED)

    Status only changes through payments.services, which guards every transition.
    Ledger lines for a payment carry the payment's reference, like transfers do.
    """

    class Direction(models.TextChoices):
        IN = "IN", "Deposit"
        OUT = "OUT", "Withdrawal"

    class Method(models.TextChoices):
        STK = "STK", "M-Pesa STK Push"
        C2B = "C2B", "M-Pesa Paybill"
        B2C = "B2C", "M-Pesa B2C"
        PAYPAL_ORDER = "PAYPAL_ORDER", "PayPal Checkout"
        PAYPAL_PAYOUT = "PAYPAL_PAYOUT", "PayPal Payout"
        BANK_OUT = "BANK_OUT", "Bank payout"
        FAKE_IN = "FAKE_IN", "Fake deposit"
        FAKE_OUT = "FAKE_OUT", "Fake payout"

    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        PENDING = "PENDING", "Pending"
        HELD = "HELD", "Held"
        SUBMITTED = "SUBMITTED", "Submitted"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        EXPIRED = "EXPIRED", "Expired"
        REVERSED = "REVERSED", "Reversed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="external_payments")
    # Null for payments nobody started in the app, e.g. a Paybill deposit made from a bank app.
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="external_payments"
    )
    direction = models.CharField(max_length=3, choices=Direction.choices)
    rail = models.CharField(max_length=10, choices=Rail.choices)
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, choices=Account.Currency.choices)
    fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    reference = models.CharField(max_length=24, unique=True)
    provider_ref = models.CharField(max_length=64, blank=True)
    idempotency_key = models.CharField(max_length=64, blank=True)
    # Provider-specific details (phone number, PayPal order id, fake outcome). Not for secrets.
    metadata = models.JSONField(default=dict, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    # Set when the provider's record disagrees with ours (amount, currency); no money moves until a person looks.
    needs_review = models.BooleanField(default=False, db_index=True)
    review_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("rail", "provider_ref"),
                condition=~models.Q(provider_ref=""),
                name="unique_payment_provider_ref",
            ),
            models.UniqueConstraint(
                fields=("initiated_by", "idempotency_key"),
                condition=models.Q(initiated_by__isnull=False) & ~models.Q(idempotency_key=""),
                name="unique_payment_idempotency",
            ),
        ]
        indexes = [models.Index(fields=("status", "updated_at"))]

    def __str__(self) -> str:
        return f"{self.reference} {self.direction} {self.amount} {self.currency} ({self.status})"


class WebhookEvent(models.Model):
    """Every provider callback, stored before it is processed so nothing is lost or applied twice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rail = models.CharField(max_length=10, choices=Rail.choices)
    event_id = models.CharField(max_length=128)
    headers = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict)
    payment = models.ForeignKey(
        ExternalPayment, on_delete=models.SET_NULL, null=True, blank=True, related_name="webhook_events"
    )
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ("-received_at",)
        constraints = [models.UniqueConstraint(fields=("rail", "event_id"), name="unique_webhook_event")]

    def __str__(self) -> str:
        return f"{self.rail} {self.event_id}"
