"""Bills (payables) and invoices (receivables) in a business's books, paid through its one cashbook."""

from decimal import Decimal

from accounting import reports
from accounting.models import BusinessEntry, Invoice, LedgerAccount
from accounting.services import business_date
from banking.services import transfer_funds
from organizations import services as orgs
from organizations.models import Membership

from .tests import PayrollTestCase

D = Decimal


class InvoiceTestCase(PayrollTestCase):
    def setUp(self):
        super().setUp()
        self.org.approval_threshold = D("1000000")  # payments go straight out
        self.org.save()
        self.supplier, self.customer = self.workers[1], self.workers[2]

    def category(self, role):
        self.client.get(self.url("books/categories/"))  # creates the standard chart
        return LedgerAccount.objects.get(organization=self.org, role=role)

    def record(self, kind, amount, role, party="Mama Mboga Supplies", **extra):
        body = {"kind": kind, "party": party, "amount": amount, "category_id": self.category(role).id, **extra}
        res = self.client.post(self.url("books/invoices/"), body)
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def pay_supplier(self, amount, key):
        """A real payment out of the business cashbook to the supplier's FluxPay account."""
        membership = Membership.objects.select_related("organization", "user").get(organization=self.org, user=self.owner)
        orgs.create_payment(membership=membership, amount=D(amount), note="Supplier", idempotency_key=key,
                            type="SUPPLIER", destination_account_number=self.supplier.account_number)  # fmt: skip
        return BusinessEntry.objects.filter(organization=self.org, direction="OUT", reference__isnull=False).first()

    def customer_pays(self, amount, key):
        transfer_funds(user=self.customer.owner, source_id=self.customer.id,
                       destination_number=self.business.account_number, amount=D(amount), note="",
                       idempotency_key=key)  # fmt: skip
        return BusinessEntry.objects.filter(organization=self.org, direction="IN", amount=D(amount)).first()

    def books(self):
        today = business_date()
        pl = reports.income_statement("KES", today.replace(day=1), today, organization=self.org)
        bs = reports.balance_sheet("KES", today, organization=self.org)
        income, expenses, assets, liabilities = (
            {r.account.name: r.amount for r in section.rows}
            for section in (pl["income"], pl["expenses"], bs["assets"], bs["liabilities"])
        )
        return income, expenses, assets, liabilities, bs["balanced"]


class BillTests(InvoiceTestCase):
    def test_bill_is_owed_then_paid_through_the_cashbook_without_counting_the_expense_twice(self):
        bill = self.record("BILL", "3000", "suppliers", due_date=business_date().isoformat())
        self.assertEqual(bill["number"], "BILL-0001")
        _, expenses, _, liabilities, balanced = self.books()
        self.assertEqual(expenses, {"Purchases and suppliers": D("3000")})
        self.assertEqual(liabilities, {"Accounts payable": D("3000")})
        self.assertTrue(balanced)

        entry = self.pay_supplier("3000", "pay-bill-1")
        candidates = self.client.get(self.url(f"books/invoices/{bill['id']}/payable-entries/")).data
        self.assertEqual([c["id"] for c in candidates], [str(entry.id)])
        res = self.client.post(self.url(f"books/invoices/{bill['id']}/pay/"), {"entry_id": str(entry.id)})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data["status"], res.data["outstanding"]), ("PAID", "0.00"))

        _, expenses, _, liabilities, balanced = self.books()
        self.assertEqual(expenses, {"Purchases and suppliers": D("3000")})  # once, not twice
        self.assertEqual(liabilities, {})
        self.assertTrue(balanced)
        entry.refresh_from_db()
        self.assertEqual(entry.category.name, "Accounts payable")

    def test_a_linked_payment_cant_be_refiled_or_reused(self):
        bill = self.record("BILL", "3000", "suppliers")
        other = self.record("BILL", "3000", "suppliers", party="Another supplier")
        entry = self.pay_supplier("3000", "pay-bill-2")
        self.client.post(self.url(f"books/invoices/{bill['id']}/pay/"), {"entry_id": str(entry.id)})
        res = self.client.post(self.url(f"books/invoices/{other['id']}/pay/"), {"entry_id": str(entry.id)})
        self.assertEqual(res.data["error"]["code"], "entry_already_linked")
        res = self.client.patch(self.url(f"books/entries/{entry.id}/"), {"category_id": self.category("expenses").id})
        self.assertEqual(res.data["error"]["code"], "cannot_reclassify")

    def test_payables_and_receivables_cant_be_chosen_as_categories(self):
        self.record("BILL", "100", "suppliers")
        names = {c["name"] for c in self.client.get(self.url("books/categories/")).data}
        self.assertIn("Interest earned", names)
        self.assertFalse(names & {"Accounts payable", "Accounts receivable"})

    def test_overpayment_and_wrong_direction_are_refused(self):
        bill = self.record("BILL", "1000", "suppliers")
        entry = self.pay_supplier("3000", "pay-bill-3")
        res = self.client.post(self.url(f"books/invoices/{bill['id']}/pay/"), {"entry_id": str(entry.id)})
        self.assertEqual(res.data["error"]["code"], "overpayment")
        money_in = self.customer_pays("500", "in-1")
        res = self.client.post(self.url(f"books/invoices/{bill['id']}/pay/"), {"entry_id": str(money_in.id)})
        self.assertEqual(res.data["error"]["code"], "wrong_direction")

    def test_bill_needs_an_expense_category(self):
        res = self.client.post(self.url("books/invoices/"), {"kind": "BILL", "party": "X", "amount": "100",
                                                              "category_id": self.category("sales").id})  # fmt: skip
        self.assertEqual(res.data["error"]["code"], "invalid_category")

    def test_cancel_reverses_the_bill_but_not_once_paid(self):
        bill = self.record("BILL", "2000", "suppliers")
        res = self.client.post(self.url(f"books/invoices/{bill['id']}/cancel/"), {"reason": "Entered twice"})
        self.assertEqual(res.data["status"], "CANCELLED")
        _, expenses, _, liabilities, balanced = self.books()
        self.assertEqual((expenses, liabilities, balanced), ({}, {}, True))

        paid = self.record("BILL", "3000", "suppliers")
        entry = self.pay_supplier("3000", "pay-bill-4")
        self.client.post(self.url(f"books/invoices/{paid['id']}/pay/"), {"entry_id": str(entry.id)})
        res = self.client.post(self.url(f"books/invoices/{paid['id']}/cancel/"), {"reason": "Changed my mind"})
        self.assertEqual(res.data["error"]["code"], "invoice_has_payments")

    def test_viewers_see_bills_but_cant_record_them(self):
        viewer = self.member("viewer@kamau.test", "Vera Viewer", Membership.Role.VIEWER)
        self.client.force_authenticate(viewer)
        self.assertEqual(self.client.get(self.url("books/invoices/")).status_code, 200)
        res = self.client.post(self.url("books/invoices/"), {"kind": "BILL", "party": "X", "amount": "1",
                                                              "category_id": 1})  # fmt: skip
        self.assertEqual(res.status_code, 403)


class InvoiceCollectionTests(InvoiceTestCase):
    def test_invoice_collected_in_two_parts(self):
        invoice = self.record("INVOICE", "800", "sales", party="Hotel Paradise")
        self.assertEqual(invoice["number"], "INV-0001")
        income, _, assets, _, _ = self.books()
        self.assertEqual(income, {"Sales and revenue": D("800")})
        self.assertEqual(assets["Accounts receivable"], D("800"))

        for i, amount in enumerate(("300", "500")):
            entry = self.customer_pays(amount, f"customer-{i}")
            res = self.client.post(self.url(f"books/invoices/{invoice['id']}/pay/"), {"entry_id": str(entry.id)})
            self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data["status"], res.data["paid_amount"]), ("PAID", "800.00"))

        income, _, assets, _, balanced = self.books()
        self.assertEqual(income, {"Sales and revenue": D("800")})  # the receipts aren't sales a second time
        self.assertNotIn("Accounts receivable", assets)
        self.assertTrue(balanced)

    def test_list_shows_whats_owed_each_way(self):
        self.record("INVOICE", "800", "sales", party="Hotel Paradise")
        self.record("BILL", "300", "expenses", party="KPLC", due_date="2020-01-31", issue_date="2020-01-01")
        data = self.client.get(self.url("books/invoices/"), {"open": 1}).data
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["totals"]["receivable"], "800.00")
        self.assertEqual((data["totals"]["payable"], data["totals"]["payable_overdue"]), ("300.00", "300.00"))
        self.assertEqual(Invoice.objects.get(number="BILL-0001").issue_date.isoformat(), "2020-01-01")
