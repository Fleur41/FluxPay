"""Test helpers that configure business rules the way staff would in admin (platform_settings)."""
from decimal import Decimal

from platform_settings.models import Currency


def platform_rules(currency: str = "KES", **fields):
    """Class decorator: before each test, set fields on `currency`, e.g. signup_bonus="1000.00".

    Tests fund wallets this way (a staff-configured promotion), never through code defaults.
    Changes roll back with each test like any other database write.
    """
    values = {name: Decimal(value) for name, value in fields.items()}

    def decorate(cls):
        original = cls.setUp

        def setUp(self):
            Currency.objects.filter(code=currency).update(**values)
            original(self)

        cls.setUp = setUp
        return cls

    return decorate


# The amount most tests start each new wallet with.
funded = platform_rules(signup_bonus="1000.00")
