from django.conf import settings
from django.utils.module_loading import import_string

from .base import PaymentProvider


def get_provider(rail: str) -> PaymentProvider:
    """The adapter configured for a rail in FLUXPAY_PAYMENT_PROVIDERS. Raises LookupError if none is."""
    path = settings.FLUXPAY_PAYMENT_PROVIDERS.get(rail)
    if not path:
        raise LookupError(f"No payment provider is configured for {rail}.")
    return import_string(path)()
