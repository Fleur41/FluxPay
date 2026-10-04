"""Starting values, matching how FluxPay behaved before these rules moved out of the code.

Staff change them in Django admin afterwards; nothing reads these numbers from code. The signup bonus
starts at 0: money only enters FluxPay through a real payment, or a promotion staff deliberately set.
"""
from decimal import Decimal

from django.db import migrations

CURRENCIES = [
    # code, name, sort order
    ("KES", "Kenyan Shilling", 0),
    ("USD", "US Dollar", 1),
    ("EUR", "Euro", 2),
    ("GBP", "British Pound", 3),
]


def create(apps, schema_editor):
    Currency = apps.get_model("platform_settings", "Currency")
    PlatformSettings = apps.get_model("platform_settings", "PlatformSettings")
    for code, name, order in CURRENCIES:
        Currency.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "sort_order": order,
                "min_transfer": Decimal("1.00"),
                "max_transfer": Decimal("500000.00"),
                "signup_bonus": Decimal("0.00"),
            },
        )
    PlatformSettings.objects.get_or_create(
        id=1,
        defaults={
            "default_currency_id": "KES",
            "statement_max_days": 366,
            "invitation_expiry_days": 7,
            "session_timeout_minutes": 5,
            "budget_needs_percent": 50,
            "budget_wants_percent": 30,
            "budget_savings_percent": 20,
        },
    )


class Migration(migrations.Migration):
    dependencies = [("platform_settings", "0001_initial")]

    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
