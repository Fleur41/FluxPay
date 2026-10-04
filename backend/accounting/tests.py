"""The books: cashbook entries, allocations to wallets, journals, reports and reconciliation."""

import importlib
from datetime import timedelta
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models import Sum
from django.test import TestCase, override_settings

from audit.models import AuditEvent
from banking.models import Account, ManualAdjustment
from banking.services import open_wallet, post_adjustment, transfer_funds
from fluxpay.exceptions import BusinessError
from fluxpay.testing import platform_rules
from organizations import services as org_services
from payments.models import ExternalPayment
from payments.providers.base import ProviderState, StatusResult
from payments.tests import PaymentTestMixin, payment_settings

from . import reports, services
from .models import AccountingSettings, BankAccount, CashbookEntry, JournalEntry, LedgerAccount

User = get_user_model()
PASSWORD = "Str0ng-Pass!42"
REASON = "Cash deposited at the Nairobi office, slip 1042"
D = Decimal


def balance(role, currency="KES"):
    """A system ledger account's balance on its normal side."""
    gl = services.ledger(role, currency)
    totals = gl.lines.aggregate(dr=Sum("debit"), cr=Sum("credit"))
    dr, cr = totals["dr"] or D(0), totals["cr"] or D(0)
    return dr - cr if gl.debit_normal else cr - dr


class BooksTestCase(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("cashier@fluxpay.test", PASSWORD, full_name="Cate Cashier", is_staff=True)
        self.other_staff = User.objects.create_user("ops@fluxpay.test", PASSWORD, full_name="Opal Ops", is_staff=True)
        self.customer = User.objects.create_user("simon@example.com", PASSWORD, full_name="Simon Kip")
        self.wallet = open_wallet(self.customer)
        self.safe = services.open_bank_account(
            name="Equity – customer funds", bank_name="Equity Bank", account_number="0170012345", branch="Moi Avenue",
            currency="KES", purpose=BankAccount.Purpose.SAFEGUARDING, is_active=True,
        )  # fmt: skip
        self.operating = services.open_bank_account(
            name="Equity – operating", bank_name="Equity Bank", account_number="0170099999", branch="Moi Avenue",
            currency="KES", purpose=BankAccount.Purpose.OPERATING, is_active=True,
        )  # fmt: skip
        self.today = services.business_date()

    def cash(self, category, amount, bank=None, **kwargs):
        return services.record_cashbook_entry(
            staff=kwargs.pop("staff", self.staff),
            bank=bank or self.safe,
            category=category,
            amount=D(amount),
            date=kwargs.pop("date", self.today),
            counterparty=kwargs.pop("counterparty", "Simon Kip"),
            description=kwargs.pop("description", "Cash at the counter"),
            **kwargs,
        )

    def allocate(self, receipt, amount, wallet=None, kind="CREDIT", staff=None):
        return post_adjustment(
            staff=staff or self.other_staff,
            account_id=(wallet or self.wallet).id,
            kind=kind,
            amount=D(amount),
            reason=REASON,
            cashbook_entry=receipt,
        )

    def refresh(self, *objs):
        for obj in objs:
            obj.refresh_from_db()

    def assert_books_balance(self, currency="KES"):
        tb = reports.trial_balance(currency, self.today)
        self.assertTrue(tb["balanced"], tb)
        bs = reports.balance_sheet(currency, self.today)
        self.assertTrue(bs["balanced"], (bs["assets"].total, bs["liabilities_and_equity"]))
        self.assertEqual(reports.safeguarding(currency)["subledger_difference"], 0)


class ChartAndNumberingTests(BooksTestCase):
    def test_bank_accounts_get_their_own_ledger_accounts(self):
        self.assertEqual((self.safe.ledger_account.code, self.operating.ledger_account.code), ("1010", "1011"))
        self.assertEqual(self.safe.ledger_account.type, LedgerAccount.Type.ASSET)
        self.assertTrue(self.safe.ledger_account.is_control)

    def test_documents_are_numbered_without_gaps(self):
        first = self.cash("CUSTOMER_DEPOSIT", "100")
        second = self.cash("CAPITAL", "100")
        expense = self.cash("BANK_CHARGES", "10")
        self.assertEqual((first.number, second.number, expense.number), ("RCT-000001", "RCT-000002", "PAY-000001"))
        self.assertEqual(first.journal.number, "JE-000001")


class CashbookTests(BooksTestCase):
    def test_customer_deposit_waits_as_an_unallocated_receipt(self):
        receipt = self.cash("CUSTOMER_DEPOSIT", "5000")
        self.assertEqual(receipt.direction, "RECEIPT")
        self.assertEqual(services.bank_balance(self.safe), D("5000"))
        self.assertEqual(balance("unallocated_receipts"), D("5000"))
        self.assertEqual(balance("customer_funds"), D("0"))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, D("0"))  # nobody has been credited yet
        self.assertTrue(AuditEvent.objects.filter(action="cashbook.receipt").exists())
        self.assert_books_balance()

    def test_customer_money_only_goes_through_safeguarding_accounts(self):
        with self.assertRaises(BusinessError):
            self.cash("CUSTOMER_DEPOSIT", "5000", bank=self.operating)

    def test_capital_interest_charges_expenses_and_drawings(self):
        self.cash("CAPITAL", "100000", bank=self.operating, counterparty="The owners")
        self.cash("INTEREST", "250", bank=self.operating, counterparty="Equity Bank")
        rent = LedgerAccount.objects.create(code="5910", name="Rent", type="EXPENSE", currency="KES")
        self.cash("EXPENSE", "30000", bank=self.operating, counterparty="Landlord", ledger_account=rent)
        self.cash("BANK_CHARGES", "150", bank=self.operating, counterparty="Equity Bank")
        self.cash("DRAWINGS", "10000", bank=self.operating, counterparty="The owners")
        self.assertEqual(services.bank_balance(self.operating), D("60100"))

        pl = reports.income_statement("KES", self.today.replace(day=1), self.today)
        self.assertEqual(pl["income"].total, D("250"))
        self.assertEqual(
            {r.account.code: r.amount for r in pl["expenses"].rows}, {"5000": D("150"), "5910": D("30000")}
        )
        self.assertEqual(pl["profit"], D("-29900"))

        bs = reports.balance_sheet("KES", self.today)
        equity = {r.account.code: r.amount for r in bs["equity"].rows}
        self.assertEqual(equity, {"3000": D("100000"), "3100": D("-10000")})
        self.assertEqual(bs["equity"].extra, [("Profit (loss) to date", D("-29900"))])
        self.assertEqual(bs["equity"].total, D("60100"))
        self.assert_books_balance()

    def test_payments_cannot_exceed_what_the_cashbook_holds(self):
        self.cash("CAPITAL", "1000", bank=self.operating)
        with self.assertRaises(BusinessError) as ctx:
            self.cash("EXPENSE", "1000.01", bank=self.operating)
        self.assertIn("only 1,000.00", str(ctx.exception.detail))

    def test_expense_account_must_be_an_expense(self):
        self.cash("CAPITAL", "1000", bank=self.operating)
        with self.assertRaises(BusinessError):
            self.cash("EXPENSE", "10", bank=self.operating, ledger_account=services.ledger("interest_income", "KES"))

    def test_transfer_between_bank_accounts(self):
        self.cash("CAPITAL", "50000", bank=self.operating)
        out = self.cash("BANK_TRANSFER", "20000", bank=self.operating, transfer_to=self.safe)
        self.assertEqual(services.bank_balance(self.operating), D("30000"))
        self.assertEqual(services.bank_balance(self.safe), D("20000"))
        incoming = out.counterpart
        self.assertEqual((incoming.bank_account, incoming.direction), (self.safe, "RECEIPT"))
        self.assertEqual(out.journal_id, incoming.journal_id)
        self.assert_books_balance()

    def test_future_dates_and_closed_periods_are_refused(self):
        with self.assertRaises(BusinessError):
            self.cash("CAPITAL", "10", date=self.today + timedelta(days=1))
        AccountingSettings.objects.update_or_create(
            id=1, defaults={"books_closed_until": self.today - timedelta(days=1)}
        )
        with self.assertRaises(BusinessError) as ctx:
            self.cash("CAPITAL", "10", date=self.today - timedelta(days=1))
        self.assertEqual(ctx.exception.error_code, "cashbook_invalid")
        self.assertIn("closed", str(ctx.exception.detail))
        self.cash("CAPITAL", "10")  # today is still open


class AllocationTests(BooksTestCase):
    def test_top_up_comes_out_of_the_receipt(self):
        receipt = self.cash("CUSTOMER_DEPOSIT", "5000")
        adjustment = self.allocate(receipt, "3000")
        self.refresh(receipt, self.wallet)
        self.assertEqual(self.wallet.balance, D("3000"))
        self.assertEqual((receipt.allocated, receipt.unallocated), (D("3000"), D("2000")))
        self.assertEqual(adjustment.cashbook_entry, receipt)
        self.assertEqual(balance("customer_funds"), D("3000"))
        self.assertEqual(balance("unallocated_receipts"), D("2000"))
        sg = reports.safeguarding("KES")
        self.assertEqual((sg["held"], sg["owed"], sg["backed"]), (D("5000"), D("5000"), True))
        self.assert_books_balance()

    def test_cannot_allocate_more_than_was_received(self):
        receipt = self.cash("CUSTOMER_DEPOSIT", "5000")
        self.allocate(receipt, "4000")
        with self.assertRaises(BusinessError) as ctx:
            self.allocate(receipt, "1000.01")
        self.assertEqual(ctx.exception.error_code, "receipt_unavailable")
        self.assertIn("Only 1,000.00 KES", str(ctx.exception.detail))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, D("4000"))

    def test_a_top_up_needs_a_receipt(self):
        with self.assertRaises(BusinessError) as ctx:
            post_adjustment(
                staff=self.staff, account_id=self.wallet.id, kind="CREDIT", amount=D("10"), reason=REASON,
                cashbook_entry=None,
            )  # fmt: skip
        self.assertEqual(ctx.exception.error_code, "receipt_required")

    def test_only_customer_deposits_can_be_allocated(self):
        capital = self.cash("CAPITAL", "5000")
        with self.assertRaises(BusinessError):
            self.allocate(capital, "100")

    def test_currencies_must_match(self):
        usd_customer = User.objects.create_user("usd@example.com", PASSWORD, full_name="Dollar Dan")
        usd_wallet = open_wallet(usd_customer, currency="USD")
        receipt = self.cash("CUSTOMER_DEPOSIT", "5000")
        with self.assertRaises(BusinessError) as ctx:
            self.allocate(receipt, "100", wallet=usd_wallet)
        self.assertIn("in KES; the wallet is in USD", str(ctx.exception.detail))

    def test_one_receipt_can_be_split_across_wallets(self):
        friend = User.objects.create_user("friend@example.com", PASSWORD, full_name="Faith Friend")
        friend_wallet = open_wallet(friend)
        org = org_services.create_organization(user=self.customer, name="Kip Traders")
        receipt = self.cash("CUSTOMER_DEPOSIT", "9000")
        self.allocate(receipt, "2000")
        self.allocate(receipt, "3000", wallet=friend_wallet)
        self.allocate(receipt, "4000", wallet=org.accounts.get())
        receipt.refresh_from_db()
        self.assertEqual(receipt.unallocated, D("0"))
        sg = reports.safeguarding("KES")
        self.assertEqual((sg["personal_wallets"], sg["business_wallets"]), (D("5000"), D("4000")))
        self.assert_books_balance()

    def test_correction_returns_money_to_the_receipt(self):
        receipt = self.cash("CUSTOMER_DEPOSIT", "5000")
        self.allocate(receipt, "5000")
        self.allocate(receipt, "1500", kind="DEBIT")  # credited to the wrong wallet: take some back
        self.refresh(receipt, self.wallet)
        self.assertEqual(self.wallet.balance, D("3500"))
        self.assertEqual(receipt.unallocated, D("1500"))
        self.assertEqual(balance("unallocated_receipts"), D("1500"))
        self.assert_books_balance()

    def test_correction_cannot_return_more_than_was_allocated_from_that_receipt(self):
        first, second = self.cash("CUSTOMER_DEPOSIT", "1000"), self.cash("CUSTOMER_DEPOSIT", "1000")
        self.allocate(first, "1000")
        self.allocate(second, "200")
        with self.assertRaises(BusinessError) as ctx:
            self.allocate(second, "500", kind="DEBIT")
        self.assertIn("Only 200.00 KES of", str(ctx.exception.detail))

    def test_segregation_of_duties_when_switched_on(self):
        AccountingSettings.objects.update_or_create(id=1, defaults={"require_second_person": True})
        receipt = self.cash("CUSTOMER_DEPOSIT", "1000", staff=self.staff)
        with self.assertRaises(BusinessError) as ctx:
            self.allocate(receipt, "100", staff=self.staff)
        self.assertIn("a colleague must credit the wallet", str(ctx.exception.detail))
        self.allocate(receipt, "100", staff=self.other_staff)


class PayoutTests(BooksTestCase):
    def test_cash_withdrawal_debits_the_wallet_and_the_bank(self):
        receipt = self.cash("CUSTOMER_DEPOSIT", "5000")
        self.allocate(receipt, "5000")
        payout = self.cash("CUSTOMER_PAYOUT", "1200", wallet=self.wallet, counterparty="Simon Kip")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, D("3800"))
        self.assertEqual(services.bank_balance(self.safe), D("3800"))
        adjustment = ManualAdjustment.objects.get(kind="PAYOUT")
        self.assertEqual((adjustment.cashbook_entry, adjustment.amount), (payout, D("1200")))
        self.assertIsNotNone(payout.journal)
        self.assertTrue(AuditEvent.objects.filter(action="adjustment.paid_out").exists())
        self.assert_books_balance()
        self.assertTrue(reports.safeguarding("KES")["backed"])

    def test_cannot_pay_out_more_than_the_wallet_holds(self):
        receipt = self.cash("CUSTOMER_DEPOSIT", "5000")
        self.allocate(receipt, "1000")
        with self.assertRaises(BusinessError) as ctx:
            self.cash("CUSTOMER_PAYOUT", "1000.01", wallet=self.wallet)
        self.assertIn("The wallet only holds 1,000.00 KES", str(ctx.exception.detail))
        self.assertFalse(CashbookEntry.objects.filter(category="CUSTOMER_PAYOUT").exists())


class ReversalTests(BooksTestCase):
    def test_wrong_receipt_is_reversed_not_deleted(self):
        receipt = self.cash("CUSTOMER_DEPOSIT", "5000")
        reversal = services.reverse_cashbook_entry(staff=self.staff, entry=receipt, reason="Recorded twice: slip 1042")
        self.assertEqual((reversal.direction, reversal.category, reversal.reverses), ("PAYMENT", "REVERSAL", receipt))
        self.assertEqual(services.bank_balance(self.safe), D("0"))
        self.assertEqual(balance("unallocated_receipts"), D("0"))
        self.assertEqual(reversal.journal.reverses, receipt.journal)
        self.assertEqual(CashbookEntry.objects.count(), 2)  # both stay in the books
        with self.assertRaises(BusinessError):
            services.reverse_cashbook_entry(staff=self.staff, entry=receipt, reason="Recorded twice: slip 1042")
        with self.assertRaises(BusinessError):
            self.allocate(CashbookEntry.objects.get(pk=receipt.pk), "1")  # a reversed receipt can't be used
        self.assert_books_balance()

    def test_allocated_receipts_and_payouts_cannot_be_reversed(self):
        receipt = self.cash("CUSTOMER_DEPOSIT", "5000")
        self.allocate(receipt, "100")
        with self.assertRaises(BusinessError) as ctx:
            services.reverse_cashbook_entry(staff=self.staff, entry=receipt, reason="Typed the wrong amount")
        self.assertIn("Take it back with corrections", str(ctx.exception.detail))
        payout = self.cash("CUSTOMER_PAYOUT", "50", wallet=self.wallet)
        with self.assertRaises(BusinessError):
            services.reverse_cashbook_entry(staff=self.staff, entry=payout, reason="Customer brought it back")

    def test_reversing_a_bank_transfer_reverses_both_halves(self):
        self.cash("CAPITAL", "5000", bank=self.operating)
        out = self.cash("BANK_TRANSFER", "2000", bank=self.operating, transfer_to=self.safe)
        services.reverse_cashbook_entry(staff=self.staff, entry=out, reason="Went to the wrong account")
        self.assertEqual(services.bank_balance(self.operating), D("5000"))
        self.assertEqual(services.bank_balance(self.safe), D("0"))
        self.assert_books_balance()


class ManualJournalTests(BooksTestCase):
    def test_balanced_journal_posts_and_can_be_reversed(self):
        promotions, opening = services.ledger("promotions", "KES"), services.ledger("opening_balance", "KES")
        entry = services.post_manual_journal(
            staff=self.staff, date=self.today, memo="Reclassify bonuses",
            lines=[(promotions, D("100"), 0, ""), (opening, 0, D("100"), "")],
        )  # fmt: skip
        self.assertEqual(entry.source, "MANUAL")
        reversal = services.reverse_manual_journal(staff=self.staff, entry=entry, reason="Posted to the wrong month")
        self.assertEqual(reversal.reverses, entry)
        self.assertEqual(balance("promotions"), D("0"))

    def test_unbalanced_and_control_account_journals_are_refused(self):
        promotions, opening = services.ledger("promotions", "KES"), services.ledger("opening_balance", "KES")
        with self.assertRaises(BusinessError) as ctx:
            services.post_manual_journal(
                staff=self.staff, date=self.today, memo="Oops",
                lines=[(promotions, D("100"), 0, ""), (opening, 0, D("99"), "")],
            )  # fmt: skip
        self.assertEqual(ctx.exception.error_code, "journal_unbalanced")
        with self.assertRaises(BusinessError) as ctx:
            services.post_manual_journal(
                staff=self.staff, date=self.today, memo="Sneaky top-up",
                lines=[(services.ledger("customer_funds", "KES"), 0, D("100"), ""), (opening, D("100"), 0, "")],
            )  # fmt: skip
        self.assertEqual(ctx.exception.error_code, "control_account")


@payment_settings
@platform_rules(signup_bonus="250.00")
class WalletActivityStaysInStepTests(PaymentTestMixin, BooksTestCase):  # setUp opens a wallet too
    """Whatever happens in the wallets, the control account equals their total."""

    def test_bonuses_transfers_and_provider_payments(self):
        self.user, self.wallet = self.make_user()  # gets the 250 welcome bonus
        friend, friend_wallet = self.make_user("friend@example.com", "Faith Friend")
        self.assertEqual(balance("promotions"), D("750"))  # an expense: three welcome bonuses so far
        transfer_funds(
            user=self.user, source_id=self.wallet.id, destination_number=friend_wallet.account_number,
            amount=D("100"), note="", idempotency_key="t-1",
        )  # fmt: skip
        deposit = self.deposit("400.00")
        from payments import services as payments

        payments.complete_payment(
            deposit.id, StatusResult(state=ProviderState.SUCCEEDED, amount=D("400.00"), currency="KES")
        )
        payout = self.payout("50.00")
        payments.fail_payment(payout.id, "Rejected by the provider")  # held money comes back
        self.assertEqual(ExternalPayment.objects.get(id=payout.id).status, "REVERSED")
        self.assertEqual(balance("provider_clearing:FAKE"), D("400"))
        self.assertEqual(balance("customer_funds"), D("1150"))  # 3 x 250 bonus + 400 deposit
        self.assert_books_balance()


class ReconciliationTests(BooksTestCase):
    def test_statement_must_agree_to_the_cent(self):
        a = self.cash("CUSTOMER_DEPOSIT", "5000")
        b = self.cash("CUSTOMER_DEPOSIT", "700")  # not on the statement yet (deposit in transit)
        with self.assertRaises(BusinessError) as ctx:
            services.reconcile_bank(
                staff=self.staff, bank=self.safe, statement_date=self.today, statement_balance=D("5000"), cleared_ids=[]
            )
        self.assertIn("out by 5,000.00 KES", str(ctx.exception.detail))
        rec = services.reconcile_bank(
            staff=self.staff, bank=self.safe, statement_date=self.today, statement_balance=D("5000"), cleared_ids=[a.pk]
        )
        self.assertEqual((rec.cashbook_balance, rec.uncleared_receipts, rec.entries_cleared), (D("5700"), D("700"), 1))
        self.refresh(a, b)
        self.assertEqual((a.cleared_on, b.cleared_on), (self.today, None))


class OpeningBalanceMigrationTests(TestCase):
    def test_existing_wallets_are_taken_on_as_an_unfunded_opening_balance(self):
        customer = User.objects.create_user("legacy@example.com", PASSWORD, full_name="Lee Gacy")
        wallet = open_wallet(customer)
        Account.objects.filter(pk=wallet.pk).update(balance=D("60150.00"))  # money from before the books
        migration = importlib.import_module("accounting.migrations.0002_settings_and_opening_balances")
        migration.take_on(django_apps, None)
        entry = JournalEntry.objects.get(source="OPENING")
        self.assertEqual(
            sorted((line.account.code, line.debit, line.credit) for line in entry.lines.all()),
            [("2000", D("0"), D("60150.00")), ("3200", D("60150.00"), D("0"))],
        )
        sg = reports.safeguarding("KES")
        self.assertEqual((sg["backed"], sg["surplus"], sg["subledger_difference"]), (False, D("-60150.00"), D("0")))


@override_settings(FLUXPAY_SMS_BACKEND="notifications.tests.RecordingSmsBackend")
class AdminFlowTests(BooksTestCase):
    def setUp(self):
        super().setUp()
        for codename in ("record_cashbook", "post_adjustment", "view_financial_reports", "reconcile_bank",
                         "view_cashbookentry", "view_bankaccount"):  # fmt: skip
            self.staff.user_permissions.add(Permission.objects.get(codename=codename))
        self.client.force_login(self.staff)

    def test_record_a_deposit_then_credit_the_wallet(self):
        res = self.client.post(
            "/admin/accounting/cashbookentry/add/",
            {
                "bank_account": self.safe.pk, "category": "CUSTOMER_DEPOSIT", "date": self.today.isoformat(),
                "amount": "2500.00", "counterparty": "Simon Kip", "bank_reference": "SLIP-77",
                "description": "Cash at the Moi Avenue branch",
            },
        )  # fmt: skip
        receipt = CashbookEntry.objects.get()
        self.assertRedirects(
            res, f"/admin/accounting/cashbookentry/{receipt.pk}/change/", fetch_redirect_response=False
        )
        page = self.client.get(res["Location"])
        self.assertContains(page, "Credit a wallet (KES 2,500.00 left)")
        self.assertContains(page, "Reverse this entry")

        form = self.client.get(f"/admin/banking/manualadjustment/add/?cashbook_entry={receipt.pk}&kind=CREDIT")
        self.assertContains(form, "RCT-000001")
        res = self.client.post(
            "/admin/banking/manualadjustment/add/",
            {
                "cashbook_entry": receipt.pk,
                "account": self.wallet.pk,
                "kind": "CREDIT",
                "amount": "2500.00",
                "reason": REASON,
            },
        )
        self.assertEqual(res.status_code, 302, res.context and res.context["adminform"].form.errors)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, D("2500.00"))

    def test_form_errors_instead_of_crashes(self):
        res = self.client.post(
            "/admin/accounting/cashbookentry/add/",
            {"bank_account": self.operating.pk, "category": "CUSTOMER_DEPOSIT", "date": self.today.isoformat(),
             "amount": "10", "counterparty": "X", "description": "Y"},
        )  # fmt: skip
        self.assertContains(res, "safeguarding")
        receipt = self.cash("CUSTOMER_DEPOSIT", "100")
        res = self.client.post(
            "/admin/banking/manualadjustment/add/",
            {
                "cashbook_entry": receipt.pk,
                "account": self.wallet.pk,
                "kind": "CREDIT",
                "amount": "100.01",
                "reason": REASON,
            },
        )
        self.assertContains(res, "Only 100.00 KES of RCT-000001 is left to allocate.")
        self.assertFalse(ManualAdjustment.objects.exists())

    def test_reports_render_and_download(self):
        receipt = self.cash("CUSTOMER_DEPOSIT", "5000")
        self.allocate(receipt, "3000")
        self.cash("CAPITAL", "20000", bank=self.operating, counterparty="The owners")
        for url, text in (
            ("/admin/accounting/reports/", "Fully backed by the bank"),
            ("/admin/accounting/reports/balance-sheet/", "Total liabilities and equity"),
            ("/admin/accounting/reports/trial-balance/", "Debits = credits"),
            ("/admin/accounting/reports/income-statement/", "Total income"),
            (
                f"/admin/accounting/reports/ledger/?account={services.ledger('customer_funds', 'KES').pk}",
                "RCT-000001 allocated",
            ),
            (f"/admin/accounting/reports/cashbook/?bank={self.safe.pk}", "2,000.00 to credit"),
            ("/admin/accounting/reports/safeguarding/", "Agrees"),
            (
                f"/admin/accounting/reports/reconcile/?bank={self.safe.pk}&statement_balance=5000",
                "Sign off reconciliation",
            ),
        ):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), text)
        csv = self.client.get("/admin/accounting/reports/trial-balance/?currency=KES&export=csv")
        self.assertEqual(csv["Content-Type"], "text/csv")
        self.assertIn("Total,25000.00,25000.00", csv.content.decode().replace("\r", ""))

    def test_reconcile_through_the_page(self):
        receipt = self.cash("CUSTOMER_DEPOSIT", "5000")
        res = self.client.post(
            "/admin/accounting/reports/reconcile/",
            {"bank": self.safe.pk, "statement_date": self.today.isoformat(), "statement_balance": "5,000.00",
             "cleared": [str(receipt.pk)]},
        )  # fmt: skip
        self.assertRedirects(res, "/admin/accounting/bankreconciliation/", fetch_redirect_response=False)
        receipt.refresh_from_db()
        self.assertEqual(receipt.cleared_on, self.today)

    def test_reports_need_permission(self):
        clerk = User.objects.create_user("clerk@fluxpay.test", PASSWORD, full_name="Cl Erk", is_staff=True)
        self.client.force_login(clerk)
        self.assertEqual(self.client.get("/admin/accounting/reports/balance-sheet/").status_code, 403)
        self.assertEqual(self.client.get("/admin/accounting/cashbookentry/add/").status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get("/admin/accounting/reports/").status_code, 302)  # to the login page
