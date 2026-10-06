"""Oversight: staff looking at a business show up in its audit log, and its books reconcile."""

from decimal import Decimal

from django.core.cache import cache

from accounting.business_reconciliation import reconcile
from audit.models import AuditEvent
from banking.models import Account, Transaction, Transfer
from users.models import User

from .tests import BusinessTestCase, personal_wallet


class StaffViewAuditTests(BusinessTestCase):
    def test_staff_opening_a_payment_is_in_the_business_audit_log(self):
        cache.clear()
        self.org.approval_threshold = Decimal("1000")
        self.org.save()
        payment = self.pay(self.owner, "100.00", "staff-view-pay-1").data
        staff = User.objects.create_superuser("ops@fluxpay.test", "Str0ng-Pass!42", full_name="Ops")
        self.client.force_login(staff)
        url = f"/admin/organizations/payment/{payment['id']}/change/"
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.get(url)  # again within minutes: one event, not two
        self.client.get("/admin/organizations/payment/", {"organization__id__exact": str(self.org.id)})

        events = AuditEvent.objects.filter(action="staff.viewed_business_data", organization_id=self.org.id)
        self.assertEqual(sorted(e.metadata["page"] for e in events), ["payment", "payments"])
        self.assertEqual({e.actor_label for e in events}, {"ops@fluxpay.test"})
        # The owner sees who at FluxPay looked.
        res = self.as_user(self.owner).get(self.url("audit-events/"), {"action": "staff.viewed_business_data"})
        self.assertEqual(len(res.data["results"]), 2)

        # A transfer between two businesses is logged for both.
        other = self.as_user(self.outsider).post("/api/v1/organizations/", {"name": "Other Co"}, format="json").data
        cashbook = Account.objects.get(organization_id=other["id"])
        transfer = self.pay(self.owner, "50.00", "staff-view-pay-2", to=cashbook.account_number).data
        transfer_id = Transfer.objects.get(reference=transfer["reference"]).id
        self.client.get(f"/admin/banking/transfer/{transfer_id}/change/")
        logged = AuditEvent.objects.filter(action="staff.viewed_business_data", target_id=str(transfer_id))
        self.assertEqual({e.organization_id for e in logged}, {self.org.id, cashbook.organization_id})


class ReconciliationTests(BusinessTestCase):
    def setUp(self):
        super().setUp()
        self.org.approval_threshold = Decimal("1000")
        self.org.save()

    def check(self):
        res = self.as_user(self.owner).get(self.url("books/reconciliation/"))
        self.assertEqual(res.status_code, 200)
        return res.data

    def test_healthy_books_match(self):
        self.pay(self.owner, "100.00", "recon-pay-1")
        report = self.check()
        self.assertTrue(report["balanced"], report["problems"])
        self.assertEqual(report["balances"], {"wallet": "700.00", "ledger": "700.00", "cashbook": "700.00"})

    def test_a_balance_changed_behind_the_ledgers_back_is_caught(self):
        Account.objects.filter(pk=self.wallet.pk).update(balance=Decimal("900.00"))
        kinds = {p["kind"] for p in self.check()["problems"]}
        self.assertEqual(kinds, {"ledger_mismatch", "cashbook_mismatch"})

    def test_money_moved_without_a_cashbook_line_is_caught(self):
        Transaction.objects.create(
            account=self.wallet, type="DEBIT", category="TRANSFER_OUT", amount=Decimal("25.00"),
            balance_after=Decimal("775.00"), reference="FPROGUE00001",
        )  # fmt: skip
        Account.objects.filter(pk=self.wallet.pk).update(balance=Decimal("775.00"))
        problems = self.check()["problems"]
        self.assertIn(("not_in_cashbook", "FPROGUE00001"), [(p["kind"], p["reference"]) for p in problems])

    def test_paying_the_same_amount_twice_in_minutes_is_flagged(self):
        self.pay(self.owner, "120.00", "recon-dup-1")
        self.pay(self.owner, "120.00", "recon-dup-2")
        report = self.check()
        self.assertTrue(report["balanced"])
        self.assertIn("possible_duplicate", [a["kind"] for a in report["attention"]])

    def test_every_business_in_this_database_reconciles(self):
        # The fixtures' businesses, after transfers, payments and a reversal.
        payment = self.pay(self.owner, "200.00", "recon-rev-1").data
        self.as_user(self.owner).post(self.url(f"payments/{payment['id']}/reverse/"), {"reason": "Wrong person"}, format="json")
        personal_wallet(self.outsider)
        from organizations.models import Organization

        for organization in Organization.objects.all():
            report = reconcile(organization)
            self.assertTrue(report["balanced"], (organization.name, report["problems"]))
