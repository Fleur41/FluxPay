"""Development data: 5 businesses, each with an owner, a finance member and 20 workers, every login with the same password.

    python manage.py seed_dev --reset            # wipe the database first (asks to confirm)
    python manage.py seed_dev --reset --yes      # ... without asking
    python manage.py seed_dev --funds 1000000    # each business cashbook's opening funds (KES)

Everything goes through the real services, so the books, ledger and audit log are as the app would make them:
workers are invited and accept; business cashbooks are funded from a recorded bank receipt by staff.
Refuses to run unless DEBUG is on.
"""

import random
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

PASSWORD = "Admin@123"
WORKERS_PER_BUSINESS = 20
BUSINESSES = [
    # name, owner's name, email domain
    ("Kamau Traders", "Grace Kamau", "kamautraders.test"),
    ("Achieng Foods", "Mercy Achieng", "achiengfoods.test"),
    ("Mwangi Construction", "Peter Mwangi", "mwangiconstruction.test"),
    ("Njeri Fashion House", "Faith Njeri", "njerifashion.test"),
    ("Otieno Logistics", "James Otieno", "otienologistics.test"),
]
FIRST_NAMES = ["Wanjiru", "Otieno", "Achieng", "Kiprono", "Njeri", "Mutua", "Akinyi", "Kamau", "Chebet", "Omondi",
               "Wairimu", "Barasa", "Nyambura", "Kipchoge", "Atieno", "Mwende", "Ochieng", "Jepkosgei", "Njoroge",
               "Moraa", "Waweru", "Adhiambo", "Kibet", "Wangari", "Odhiambo"]  # fmt: skip
LAST_NAMES = ["Mwangi", "Onyango", "Kariuki", "Wafula", "Kiplagat", "Muthoni", "Owino", "Gathoni", "Kilonzo",
              "Nduta", "Okoth", "Cherono", "Maina", "Auma", "Rotich", "Wekesa", "Kendi", "Ouma", "Njuguna", "Langat"]  # fmt: skip
JOBS = [("Cashier", 28000), ("Driver", 32000), ("Sales assistant", 26000), ("Storekeeper", 30000),
        ("Accountant", 65000), ("Supervisor", 55000), ("Cleaner", 18000), ("Security guard", 20000),
        ("Machine operator", 35000), ("Marketing officer", 48000)]  # fmt: skip


class Command(BaseCommand):
    help = "Wipes (with --reset) and fills the database with 5 businesses x 20 workers for development."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete ALL data first and rebuild the database.")
        parser.add_argument("--yes", action="store_true", help="Don't ask before deleting.")
        parser.add_argument("--funds", type=Decimal, default=Decimal("20000000000"),
                            help="KES paid into each business cashbook (default 20,000,000,000).")  # fmt: skip

    def handle(self, *args, reset, yes, funds, **options):
        if not settings.DEBUG:
            raise CommandError("seed_dev only runs with DEBUG on: it is for development databases.")
        if reset:
            if not yes and input(f"Delete ALL data in '{connection.settings_dict['NAME']}'? Type 'yes': ") != "yes":
                raise CommandError("Cancelled.")
            self.wipe()
        random.seed(2026)  # the same people every time
        # No 100 invitation SMS/emails. They're sent on commit, so the patch must outlive the transaction.
        with mock.patch("payroll.workers._send_invitation"), transaction.atomic():
            summary = self.seed(funds)
        self.report(summary)

    def wipe(self):
        """Drops every table and runs the migrations again (they also create currencies and platform settings)."""
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        else:
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA foreign_keys = OFF")
                for table in connection.introspection.table_names(cursor):
                    cursor.execute(f'DROP TABLE "{table}"')
                cursor.execute("PRAGMA foreign_keys = ON")
        call_command("migrate", interactive=False, verbosity=0)
        self.stdout.write("Database wiped and rebuilt.")

    def seed(self, funds: Decimal) -> list:
        from accounting import services as books
        from accounting.models import BankAccount, CashbookEntry
        from banking.services import open_wallet, post_adjustment
        from organizations import services as orgs
        from organizations.models import Membership
        from payroll import workers
        from platform_settings.models import Currency
        from users.models import User

        hashed = make_password(PASSWORD)  # one hash for everyone: hashing 106 passwords separately is slow

        def person(email, name, phone="", **extra):
            user = User.objects.create(email=email, full_name=name, phone_number=phone, password=hashed, **extra)
            return user

        staff = person("admin@fluxpay.dev", "FluxPay Admin", is_staff=True, is_superuser=True)
        bank = books.open_bank_account(
            name="Equity – customer funds", bank_name="Equity Bank", account_number="0170012345", branch="Moi Avenue",
            currency="KES", purpose=BankAccount.Purpose.SAFEGUARDING, is_active=True,
        )  # fmt: skip

        # The per-transaction limit guards against typing an extra zero; funding at this size needs it lifted.
        kes = Currency.objects.get(code="KES")
        limit = kes.max_transfer
        Currency.objects.filter(code="KES").update(max_transfer=max(limit, funds))

        summary, phone = [], 700100000
        for name, owner_name, domain in BUSINESSES:
            owner = person(f"owner@{domain}", owner_name, f"0{phone}")
            phone += 1
            open_wallet(owner, currency="KES")
            organization = orgs.create_organization(user=owner, name=name)
            cashbook = organization.accounts.get()
            if funds > 0:
                receipt = books.record_cashbook_entry(
                    staff=staff, bank=bank, category=CashbookEntry.Category.CUSTOMER_DEPOSIT, amount=funds,
                    date=books.business_date(), counterparty=name, description=f"Opening funds for {name}",
                    bank_reference=f"DEV-{cashbook.account_number}",
                )  # fmt: skip
                post_adjustment(staff=staff, account_id=cashbook.id, kind="CREDIT", amount=funds,
                                reason=f"Opening funds ({receipt.number})", cashbook_entry=receipt)  # fmt: skip

            membership = Membership.objects.select_related("organization", "user").get(organization=organization, user=owner)
            # A finance member prepares pay runs and payments; the owner approves them.
            finance = person(f"finance@{domain}", f"{owner_name.split()[-1]} Finance", f"0{phone}")
            phone += 1
            open_wallet(finance, currency="KES")
            Membership.objects.create(organization=organization, user=finance, role=Membership.Role.FINANCE,
                                      invited_by=owner)  # fmt: skip
            for i in range(1, WORKERS_PER_BUSINESS + 1):
                full_name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
                user = person(f"worker{i:03d}@{domain}", full_name, f"0{phone}")
                phone += 1
                wallet = open_wallet(user, currency="KES")
                job, base = random.choice(JOBS)
                salary = base + random.randrange(0, 8) * 500
                _worker, code = workers.invite(
                    membership=membership, account_number=wallet.account_number, salary_amount=salary,
                    job_title=job, employee_number=f"E{i:03d}",
                )  # fmt: skip
                workers.accept_invitation(user=user, code=code)
            cashbook.refresh_from_db()
            summary.append((name, f"owner@{domain}", f"worker001..worker{WORKERS_PER_BUSINESS:03d}@{domain}", cashbook))

        Currency.objects.filter(code="KES").update(max_transfer=limit)
        return summary

    def report(self, summary):
        self.stdout.write(self.style.SUCCESS(f"\nReady. Every login's password: {PASSWORD}\n"))
        self.stdout.write("  Staff (back office): admin@fluxpay.dev")
        for name, owner, staff_range, cashbook in summary:
            finance = owner.replace("owner@", "finance@")
            self.stdout.write(f"  {name:<22} owner: {owner:<34} finance: {finance:<36} workers: {staff_range}")
            self.stdout.write(f"  {'':<22} cashbook {cashbook.account_number}: KES {cashbook.balance:,.2f}")
