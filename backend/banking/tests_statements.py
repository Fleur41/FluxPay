import csv
import io
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from fluxpay.testing import funded

from audit.models import AuditEvent
from organizations import services as org_services
from organizations.models import Membership

from .models import Transaction
from .services import open_wallet, transfer_funds

User = get_user_model()
NAIROBI = ZoneInfo("Africa/Nairobi")


@funded
@override_settings(FLUXPAY_DISPLAY_TIMEZONE="Africa/Nairobi")
class StatementTests(APITestCase):
    def setUp(self):
        self.amina = User.objects.create_user("amina@example.com", "Str0ng-Pass!42", full_name="Amina Wanjiru")
        self.brian = User.objects.create_user("brian@example.com", "Str0ng-Pass!42", full_name="Brian Otieno")
        self.wallet, self.brian_wallet = open_wallet(self.amina), open_wallet(self.brian)
        self.at(self.wallet.transactions.get(), 2026, 8, 25)  # welcome bonus, before the period
        self.move(self.amina, self.brian_wallet, "100.00", "Lunch", (2026, 9, 3, 12))
        self.move(self.brian, self.wallet, "40.00", "Fare back", (2026, 9, 15, 23, 30))  # late evening in Nairobi
        self.move(self.amina, self.brian_wallet, "10.00", "After period", (2026, 10, 1, 8))
        self.client.force_authenticate(self.amina)

    def at(self, transaction, *parts):
        Transaction.objects.filter(id=transaction.id).update(created_at=datetime(*parts, tzinfo=NAIROBI))

    def move(self, sender, destination, amount, note, when):
        transfer, _, _ = transfer_funds(
            user=sender,
            source_id=sender.accounts.get().id,
            destination_number=destination.account_number,
            amount=Decimal(amount),
            note=note,
            idempotency_key=f"stmt-{note}",
        )
        Transaction.objects.filter(reference=transfer.reference).update(created_at=datetime(*when, tzinfo=NAIROBI))

    def download(self, **params):
        return self.client.get("/api/v1/statements/", {"date_from": "2026-09-01", "date_to": "2026-09-30", **params})

    def test_csv_statement_for_a_month(self):
        res = self.download(file_format="csv")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/csv")
        self.assertEqual(
            res["Content-Disposition"],
            f'attachment; filename="FluxPay-statement-{self.wallet.account_number}-2026-09-01-to-2026-09-30.csv"',
        )
        rows = list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))
        summary = {row[0]: row[1:] for row in rows[:9]}
        self.assertEqual(summary["Account holder"], ["Amina Wanjiru"])
        self.assertEqual(summary["Opening balance"], ["1000.00"])
        self.assertEqual(summary["Money in"], ["40.00"])
        self.assertEqual(summary["Money out"], ["100.00"])
        self.assertEqual(summary["Closing balance"], ["940.00"])

        header_index = rows.index(["Date", "Reference", "Description", "Counterparty", "Status", "Money in", "Money out", "Balance"])
        lines = rows[header_index + 1:]
        self.assertEqual([line[2] for line in lines], ["Lunch", "Fare back"])  # oldest first; nothing outside the period
        self.assertEqual(lines[0][0], "2026-09-03 12:00")  # shown in Nairobi time
        self.assertEqual(lines[0][3], f"Brian Otieno (••{self.brian_wallet.account_number[-4:]})")
        self.assertEqual(lines[0][5:], ["", "100.00", "900.00"])
        self.assertEqual(lines[1][5:], ["40.00", "", "940.00"])

    def test_pdf_statement(self):
        res = self.download(file_format="pdf")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertTrue(res.content.startswith(b"%PDF"))
        self.assertTrue(res["Content-Disposition"].endswith('.pdf"'))
        self.assertGreater(len(res.content), 1500)

    def test_pdf_by_default_and_last_30_days_when_no_dates(self):
        res = self.client.get("/api/v1/statements/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")

    def test_empty_period_still_has_balances(self):
        res = self.client.get("/api/v1/statements/", {"date_from": "2026-11-01", "date_to": "2026-11-30", "file_format": "csv"})
        summary = {row[0]: row[1:] for row in csv.reader(io.StringIO(res.content.decode("utf-8-sig"))) if row}
        self.assertEqual(summary["Opening balance"], ["930.00"])
        self.assertEqual(summary["Closing balance"], ["930.00"])

    def test_download_is_audited(self):
        self.download(file_format="csv")
        event = AuditEvent.objects.get(action="statement.downloaded")
        self.assertEqual(event.actor, self.amina)
        self.assertEqual(event.metadata, {"from": "2026-09-01", "to": "2026-09-30", "format": "csv"})

    def test_cannot_download_someone_elses_statement(self):
        res = self.download(account_id=str(self.brian_wallet.id))
        self.assertEqual(res.status_code, 404)

    def test_invalid_requests(self):
        cases = [
            {"date_from": "2026-09-30", "date_to": "2026-09-01"},
            {"date_from": "2025-01-01", "date_to": "2026-09-01"},
            {"file_format": "xlsx"},
            {"date_from": "yesterday"},
        ]
        for params in cases:
            res = self.client.get("/api/v1/statements/", params)
            self.assertEqual(res.status_code, 400, params)
            self.assertEqual(res.data["error"]["code"], "validation_error")

    def test_business_statements_need_membership(self):
        org = org_services.create_organization(user=self.brian, name="Otieno Supplies")
        business = org.accounts.get()
        self.assertEqual(self.download(account_id=str(business.id)).status_code, 404)  # not via personal endpoint
        url = f"/api/v1/organizations/{org.id}/statements/"
        self.assertEqual(self.client.get(url).status_code, 404)  # Amina isn't a member
        Membership.objects.create(organization=org, user=self.amina, role=Membership.Role.VIEWER)
        res = self.client.get(url, {"file_format": "csv"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("Otieno Supplies", res.content.decode("utf-8-sig"))
        self.assertTrue(AuditEvent.objects.filter(action="statement.downloaded", organization_id=org.id).exists())
