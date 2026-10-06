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


def customer_deposit(amount="5000.00", *, staff=None, currency="KES", counterparty="Walk-in customer"):
    """Records a customer deposit in a customer funds bank account (created on first use) and returns it.

    Wallet top-ups must be allocated from a receipt like this, as staff do in admin.
    """
    from django.contrib.auth import get_user_model

    from accounting.models import BankAccount
    from accounting.services import (
        business_date,
        open_bank_account,
        record_cashbook_entry,
    )

    User = get_user_model()
    if staff is None:
        staff, _ = User.objects.get_or_create(
            email="cashier@fluxpay.test", defaults={"full_name": "Test Cashier", "is_staff": True}
        )
    bank = BankAccount.objects.filter(currency=currency, purpose=BankAccount.Purpose.SAFEGUARDING).first()
    if bank is None:
        bank = open_bank_account(
            name=f"Test bank – customer funds {currency}",
            bank_name="Test Bank",
            account_number=f"0100{currency}",
            branch="",
            currency=currency,
            purpose=BankAccount.Purpose.SAFEGUARDING,
            is_active=True,
        )
    return record_cashbook_entry(
        staff=staff,
        bank=bank,
        category="CUSTOMER_DEPOSIT",
        amount=Decimal(amount),
        date=business_date(),
        counterparty=counterparty,
        description="Cash deposited at the Nairobi office",
        bank_reference="SLIP-1042",
    )
