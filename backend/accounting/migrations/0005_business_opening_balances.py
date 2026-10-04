"""Opens the books of businesses that already hold money: Dr their wallet, Cr Owner's capital.

From here on every movement on a business wallet is booked as it happens (accounting.business).
"""

from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import migrations
from django.utils import timezone


def open_business_books(apps, schema_editor):
    Account = apps.get_model("banking", "Account")
    LedgerAccount = apps.get_model("accounting", "LedgerAccount")
    JournalEntry = apps.get_model("accounting", "JournalEntry")
    JournalLine = apps.get_model("accounting", "JournalLine")
    BusinessEntry = apps.get_model("accounting", "BusinessEntry")
    Sequence = apps.get_model("accounting", "Sequence")

    today = timezone.localdate(timezone.now(), ZoneInfo(settings.FLUXPAY_DISPLAY_TIMEZONE))
    wallets = Account.objects.filter(organization__isnull=False, balance__gt=0).order_by("organization_id", "created_at")
    codes = {}
    for wallet in wallets:
        org_id = wallet.organization_id
        codes[org_id] = codes.get(org_id, 999) + 1
        cash = LedgerAccount.objects.create(
            organization_id=org_id, role=f"wallet:{wallet.pk}", currency=wallet.currency, code=str(codes[org_id]),
            name=f"FluxPay wallet {wallet.account_number}", type="ASSET", is_control=True,
            description="Mirrors the business wallet: every movement is posted automatically.",
        )  # fmt: skip
        capital, _ = LedgerAccount.objects.get_or_create(
            organization_id=org_id, role="capital", currency=wallet.currency,
            defaults={"code": "3000", "name": "Owner's capital", "type": "EQUITY",
                      "description": "Money the owners put into the business."},
        )  # fmt: skip
        sequence, _ = Sequence.objects.get_or_create(name=f"B{org_id.hex[:9]}")
        sequence.last += 1
        sequence.save()
        memo = "Opening balance: money in the wallet when the books started"
        journal = JournalEntry.objects.create(
            organization_id=org_id, number=f"BJ-{sequence.last:06d}", date=today, currency=wallet.currency,
            memo=memo, source="OPENING",
        )  # fmt: skip
        JournalLine.objects.create(entry=journal, account=cash, debit=wallet.balance, description=memo)
        JournalLine.objects.create(entry=journal, account=capital, credit=wallet.balance, description=memo)
        BusinessEntry.objects.create(
            organization_id=org_id, wallet=wallet, date=today, direction="IN", amount=wallet.balance,
            counterparty="Opening balance", description=memo, source="OPENING", category=capital, journal=journal,
        )  # fmt: skip


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0004_businessentry_and_more"),
        ("banking", "0008_transfer_reverses"),
    ]

    operations = [migrations.RunPython(open_business_books, migrations.RunPython.noop)]
