"""The one place code reads business rules from. Nothing here has a built-in fallback value."""
from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured

from fluxpay.exceptions import BusinessError

from .models import Currency, PlatformSettings


def platform() -> PlatformSettings:
    settings_row = PlatformSettings.objects.select_related("default_currency").filter(pk=1).first()
    if settings_row is None:
        raise ImproperlyConfigured("Platform settings are missing. Run `manage.py migrate` to create them.")
    return settings_row


def enabled_currencies():
    return Currency.objects.filter(enabled=True)


def currency(code: str) -> Currency:
    """An enabled currency, or a 400 the client can show."""
    found = Currency.objects.filter(code=(code or "").upper(), enabled=True).first()
    if found is None:
        raise BusinessError(f"{code} isn't a supported currency.", "currency_not_supported")
    return found


def check_amount(amount: Decimal, currency_code: str) -> None:
    """Enforces the currency's per-transaction minimum and maximum. Uses the currency even if since disabled,
    so existing wallets keep working under the limits staff set for it."""
    rules = Currency.objects.filter(code=currency_code).first()
    if rules is None:
        raise BusinessError(f"{currency_code} isn't a supported currency.", "currency_not_supported")
    if amount < rules.min_transfer:
        raise BusinessError(f"The smallest amount is {rules.min_transfer:,.2f} {rules.code}.", "amount_too_small")
    if amount > rules.max_transfer:
        raise BusinessError(f"The most you can send at once is {rules.max_transfer:,.2f} {rules.code}.", "limit_exceeded")
