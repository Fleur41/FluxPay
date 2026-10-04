"""Business rules that staff change in Django admin, never in code. Read them through platform_settings.services."""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Currency(models.Model):
    """A currency wallets can be opened in, with its own limits (500,000 KES and 500,000 USD are not alike)."""

    code = models.CharField(max_length=3, primary_key=True, help_text="ISO 4217 code, e.g. KES")
    name = models.CharField(max_length=60)
    enabled = models.BooleanField(default=True, help_text="New wallets can be opened in this currency.")
    sort_order = models.PositiveSmallIntegerField(default=0, help_text="Order in the app's currency lists.")
    min_transfer = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Smallest amount per transfer, payment or withdrawal.",
    )
    max_transfer = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Largest amount per transfer, payment or withdrawal.",
    )
    signup_bonus = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Credited to each new personal wallet in this currency, from the Promotions system account. "
                  "Keep at 0 unless running a promotion.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "code")
        verbose_name_plural = "currencies"

    def __str__(self) -> str:
        return f"{self.code} ({self.name})"

    def clean(self):
        self.code = (self.code or "").upper()
        if self.min_transfer is not None and self.max_transfer is not None and self.min_transfer > self.max_transfer:
            raise ValidationError({"max_transfer": "The maximum must be at least the minimum."})


class PlatformSettings(models.Model):
    """The single row (id=1) of platform-wide rules. Created by migration; edit it, never add another."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    default_currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, related_name="+", help_text="Preselected when opening a wallet."
    )
    statement_max_days = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(3660)], help_text="Longest period one statement may cover."
    )
    invitation_expiry_days = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(90)], help_text="How long a business invitation link works."
    )
    session_timeout_minutes = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(120)],
        help_text="The app signs the user out after this much inactivity.",
    )
    budget_needs_percent = models.PositiveSmallIntegerField(validators=[MaxValueValidator(100)])
    budget_wants_percent = models.PositiveSmallIntegerField(validators=[MaxValueValidator(100)])
    budget_savings_percent = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(100)], help_text="The budget planner's guideline; the three must add up to 100."
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+", editable=False
    )

    class Meta:
        verbose_name = verbose_name_plural = "platform settings"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="platform_settings_single_row")]

    def __str__(self) -> str:
        return "Platform settings"

    def clean(self):
        total = (self.budget_needs_percent or 0) + (self.budget_wants_percent or 0) + (self.budget_savings_percent or 0)
        if total != 100:
            raise ValidationError(f"The budget guideline must add up to 100% (it adds up to {total}%).")
        if self.default_currency_id and not Currency.objects.filter(code=self.default_currency_id, enabled=True).exists():
            raise ValidationError({"default_currency": "The default currency must be enabled."})
