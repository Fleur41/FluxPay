"""Creates the accounting settings row and takes on the wallets that existed before the books started.

Those balances were never matched by money in a FluxPay bank account (welcome bonuses, test deposits,
staff top-ups made before the cashbook existed), so they are opened as:

    Dr 3200 Opening balances           (equity: a deficit the owners must fund)
    Cr 2000 Customer wallet balances   (liability: what customers can spend)

The safeguarding report then shows the shortfall until capital is paid into the customer funds bank account.
"""

from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import migrations
from django.db.models import Sum
from django.utils import timezone

ACCOUNTS = {
    "customer_funds": (
        "2000",
        "Customer wallet balances",
        "LIABILITY",
        True,
        "What FluxPay owes its customers and businesses: the total of every wallet.",
    ),
    "opening_balance": (
        "3200",
        "Opening balances",
        "EQUITY",
        False,
        "Customer balances that existed before the books started, not backed by money in the bank.",
    ),
}


def take_on(apps, schema_editor):
    Account = apps.get_model("banking", "Account")
    LedgerAccount = apps.get_model("accounting", "LedgerAccount")
    JournalEntry = apps.get_model("accounting", "JournalEntry")
    JournalLine = apps.get_model("accounting", "JournalLine")
    Sequence = apps.get_model("accounting", "Sequence")
    AccountingSettings = apps.get_model("accounting", "AccountingSettings")

    AccountingSettings.objects.get_or_create(id=1)
    today = timezone.localdate(timezone.now(), ZoneInfo(settings.FLUXPAY_DISPLAY_TIMEZONE))
    totals = (
        Account.objects.filter(system_key__isnull=True)
        .values("currency")
        .annotate(total=Sum("balance"))
        .order_by("currency")
    )
    for row in totals:
        if not row["total"]:
            continue
        currency, amount = row["currency"], row["total"]
        ledger = {}
        for role, (code, name, type_, control, description) in ACCOUNTS.items():
            ledger[role], _ = LedgerAccount.objects.get_or_create(
                role=role,
                currency=currency,
                defaults={
                    "code": code,
                    "name": name,
                    "type": type_,
                    "is_control": control,
                    "description": description,
                },
            )
        sequence, _ = Sequence.objects.get_or_create(name="JE")
        sequence.last += 1
        sequence.save()
        memo = "Opening balances: customer wallets held before the books started"
        entry = JournalEntry.objects.create(
            number=f"JE-{sequence.last:06d}",
            date=today,
            currency=currency,
            memo=memo,
            source="OPENING",
        )
        JournalLine.objects.create(entry=entry, account=ledger["opening_balance"], debit=amount, description=memo)
        JournalLine.objects.create(entry=entry, account=ledger["customer_funds"], credit=amount, description=memo)


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0001_initial"),
        ("banking", "0007_manualadjustment_cashbook_entry_and_more"),
    ]

    operations = [migrations.RunPython(take_on, migrations.RunPython.noop)]
