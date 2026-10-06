"""Business money in and out by M-Pesa and bank: supplier payouts, withdrawals, deposits and staff-sent bank payouts."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings

from accounting import services as books
from accounting.models import BankAccount, BusinessEntry, CashbookEntry
from banking.models import Account
from fluxpay.celery import app as celery_app
from payments import services as payment_services
from payments.models import ExternalPayment
from payments.providers.fake import FakeProvider

from .models import Membership, Payment
from .tests import BusinessTestCase, personal_wallet

User = get_user_model()


class FakeMpesaProvider(FakeProvider):
    """Answers "succeeded" when asked, with M-Pesa's rules."""

    currencies = frozenset({"KES"})
    whole_units_only = True
    payouts_idempotent = False


RAILS = {
    "MPESA": "organizations.tests_payouts.FakeMpesaProvider",
    "BANK": "payments.providers.bank.ManualBankProvider",  # the real one: staff settle it
}


@override_settings(FLUXPAY_PAYMENT_PROVIDERS=RAILS)
class ExternalPayoutTests(BusinessTestCase):
    def setUp(self):
        super().setUp()
        conf = celery_app.conf
        saved = (conf.task_always_eager, conf.task_eager_propagates)
        conf.update(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)  # run queued jobs inline
        self.addCleanup(conf.update, CELERY_TASK_ALWAYS_EAGER=saved[0], CELERY_TASK_EAGER_PROPAGATES=saved[1])
        self.fiona = self.add_member("fiona@acme.test", "Fiona Finance", Membership.Role.FINANCE)
        self.org.approval_threshold = Decimal("1000.00")
        self.org.save()

    def beneficiary(self, name="ABC Stationery", kind="SUPPLIER", **details):
        details = details or {"method": "MPESA_PAYBILL", "paybill_number": "247247", "paybill_account": "INV-2026-001"}
        res = self.as_user(self.owner).post(
            self.url("beneficiaries/"), {"name": name, "kind": kind, **details}, format="json"
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.as_user(self.owner).post(self.url(f"beneficiaries/{res.data['id']}/verify/"))
        return res.data["id"]

    def pay(self, user, beneficiary_id, amount="250.00", key="payout-1", **extra):
        with self.captureOnCommitCallbacks(execute=True):  # submits the payout to the provider
            res = self.as_user(user).post(
                self.url("payments/"),
                {"beneficiary_id": beneficiary_id, "amount": amount, "idempotency_key": key, **extra},
                format="json",
            )
        return res

    def entries(self, reference):
        return list(
            BusinessEntry.objects.filter(wallet=self.wallet, reference=reference)
            .order_by("created_at")
            .values_list("direction", "source", "category__name")
        )

    def test_paying_a_supplier_by_mpesa(self):
        res = self.pay(self.fiona, self.beneficiary(), note="Office stationery")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data["status"], res.data["payout_method"]), ("PROCESSING", "M-Pesa to a paybill"))
        self.assertEqual(self.balance(self.wallet), Decimal("550.00"))  # left the cashbook straight away
        external = ExternalPayment.objects.get(reference=res.data["reference"])  # one reference throughout
        self.assertEqual((external.method, external.status), ("MPESA_PAYBILL", "SUBMITTED"))
        self.assertEqual(external.metadata["paybill_account"], "INV-2026-001")
        self.assertEqual(self.entries(res.data["reference"]), [("OUT", "PAYOUT", "Purchases and suppliers")])

        payment_services.check_with_provider(external.id)  # the provider confirms
        payment = Payment.objects.get(id=res.data["id"])
        self.assertEqual(payment.status, "COMPLETED")
        self.assertIsNotNone(payment.completed_at)

        reverse = self.as_user(self.owner).post(
            self.url(f"payments/{payment.id}/reverse/"), {"reason": "Wrong invoice"}, format="json"
        )
        self.assertEqual(reverse.data["error"]["code"], "not_reversible")

    def test_failed_payout_returns_the_money_to_the_cashbook(self):
        res = self.pay(self.fiona, self.beneficiary())
        payment_services.fail_payment(ExternalPayment.objects.get(reference=res.data["reference"]).id, "Invalid paybill")
        payment = Payment.objects.get(id=res.data["id"])
        self.assertEqual(payment.status, "FAILED")
        self.assertIn("Invalid paybill", payment.failure_reason)
        self.assertEqual(self.balance(self.wallet), Decimal("800.00"))
        self.assertEqual(
            self.entries(res.data["reference"]),
            [("OUT", "PAYOUT", "Purchases and suppliers"), ("IN", "PAYOUT_RETURNED", "Purchases and suppliers")],
        )

    def test_mpesa_takes_whole_shillings(self):
        res = self.pay(self.fiona, self.beneficiary(), amount="250.50")
        self.assertEqual(res.data["error"]["code"], "whole_amount_only")

    def test_bank_payout_is_sent_by_staff_and_recorded_in_fluxpays_cashbook(self):
        beneficiary = self.beneficiary(
            name="Office Landlord", kind="LANDLORD", method="BANK", bank_name="KCB",
            bank_account_name="Landlord Ltd", bank_account_number="1234567890",
        )  # fmt: skip
        res = self.pay(self.fiona, beneficiary, amount="300.00", note="October rent")
        self.assertEqual(res.data["status"], "PROCESSING")
        external = ExternalPayment.objects.get(reference=res.data["reference"])
        self.assertEqual(external.status, "SUBMITTED")  # in the staff queue
        payment_services.check_with_provider(external.id)  # nothing happens until staff act
        self.assertEqual(Payment.objects.get(id=res.data["id"]).status, "PROCESSING")

        staff = User.objects.create_user("ops@fluxpay.test", "Str0ng-Pass!42", full_name="Ops", is_staff=True)
        bank = books.open_bank_account(
            name="Equity – customer funds", bank_name="Equity Bank", account_number="0170012345",
            currency="KES", purpose=BankAccount.Purpose.SAFEGUARDING, is_active=True,
        )  # fmt: skip
        books.record_cashbook_entry(
            staff=staff, bank=bank, category=CashbookEntry.Category.CAPITAL, amount=Decimal("1000.00"),
            date=books.business_date(), counterparty="FluxPay owners", description="Opening capital",
        )  # fmt: skip
        payment_services.confirm_bank_payout(
            staff=staff, payment_id=external.id, bank=bank, bank_reference="FT26277XYZ", date=books.business_date()
        )
        self.assertEqual(Payment.objects.get(id=res.data["id"]).status, "COMPLETED")
        entry = CashbookEntry.objects.get(category="BANK_PAYOUT")
        self.assertEqual((entry.amount, entry.bank_reference, entry.counterparty), (Decimal("300.00"), "FT26277XYZ", "Landlord Ltd"))
        lines = {line.account.role: (line.debit, line.credit) for line in entry.journal.lines.select_related("account")}
        self.assertEqual(lines["provider_clearing:BANK"], (Decimal("300.00"), Decimal("0.00")))
        self.assertEqual(books.bank_balance(bank), Decimal("700.00"))
        listed = self.as_user(self.owner).get(self.url("payments/"), {"status": "COMPLETED"}).data["results"]
        self.assertEqual(listed[0]["payout_receipt"], "FT26277XYZ")

    def test_staff_can_fail_a_bank_payout_that_bounced(self):
        beneficiary = self.beneficiary(method="BANK", bank_name="KCB", bank_account_name="ABC",
                                       bank_account_number="1234567890")  # fmt: skip
        res = self.pay(self.fiona, beneficiary)
        staff = User.objects.create_user("ops@fluxpay.test", "Str0ng-Pass!42", full_name="Ops", is_staff=True)
        external = ExternalPayment.objects.get(reference=res.data["reference"])
        payment_services.staff_fail_payout(staff=staff, payment_id=external.id, reason="Bank returned it: account closed")
        self.assertEqual(Payment.objects.get(id=res.data["id"]).status, "FAILED")
        self.assertEqual(self.balance(self.wallet), Decimal("800.00"))

    def test_staff_settle_a_bank_payout_from_the_admin(self):
        beneficiary = self.beneficiary(method="BANK", bank_name="KCB", bank_account_name="ABC Ltd",
                                       bank_account_number="1234567890")  # fmt: skip
        external = ExternalPayment.objects.get(reference=self.pay(self.fiona, beneficiary).data["reference"])
        admin = User.objects.create_superuser("boss@fluxpay.test", "Str0ng-Pass!42", full_name="Boss")
        bank = books.open_bank_account(name="Equity", bank_name="Equity Bank", account_number="0170012345",
                                       currency="KES", purpose=BankAccount.Purpose.OPERATING, is_active=True)  # fmt: skip
        books.record_cashbook_entry(staff=admin, bank=bank, category=CashbookEntry.Category.CAPITAL,
                                    amount=Decimal("1000.00"), date=books.business_date(), counterparty="Owners",
                                    description="Opening capital")  # fmt: skip
        self.client.force_login(admin)
        listing = self.client.get("/admin/payments/externalpayment/", {"queue": "bank"})
        self.assertContains(listing, external.reference)
        page = self.client.get(f"/admin/payments/externalpayment/{external.pk}/settle/")
        self.assertContains(page, "1234567890")  # what staff need to send it
        res = self.client.post(f"/admin/payments/externalpayment/{external.pk}/settle/", {
            "outcome": "sent", "bank_account": bank.pk, "date": books.business_date().isoformat(), "receipt": "FT1",
        })  # fmt: skip
        self.assertEqual(res.status_code, 302)
        external.refresh_from_db()
        self.assertEqual(external.status, "COMPLETED")
        self.assertEqual(Payment.objects.get(external_payment=external).status, "COMPLETED")

    def test_only_owners_withdraw_and_it_is_filed_as_drawings(self):
        own = self.beneficiary(name="Acme M-Pesa", kind="OWN_ACCOUNT", method="MPESA_MOBILE", mpesa_phone="0712345678")
        self.assertEqual(self.pay(self.fiona, own, key="withdraw-finance").status_code, 403)
        res = self.pay(self.owner, own, amount="500.00", key="withdraw-owner")
        self.assertEqual((res.data["type"], res.data["status"]), ("WITHDRAWAL", "PROCESSING"))
        external = ExternalPayment.objects.get(reference=res.data["reference"])
        self.assertEqual((external.method, external.metadata["mpesa_phone"]), ("MPESA_B2C", "+254712345678"))
        self.assertEqual(self.entries(res.data["reference"]), [("OUT", "PAYOUT", "Owner's drawings")])

    def test_mpesa_deposit_into_the_cashbook(self):
        with self.captureOnCommitCallbacks(execute=True):
            res = self.as_user(self.fiona).post(
                self.url("deposits/mpesa/"),
                {"phone_number": "0712 345 678", "amount": "1500", "idempotency_key": "biz-deposit-1"},
                format="json",
            )
        self.assertEqual(res.status_code, 202, res.data)
        payment_services.check_with_provider(res.data["id"])
        self.assertEqual(self.balance(self.wallet), Decimal("2300.00"))
        self.assertEqual(self.entries(res.data["reference"]), [("IN", "PROVIDER_DEPOSIT", "Owner's capital")])
        listed = self.as_user(self.owner).get(self.url("external-payments/")).data["results"]
        self.assertEqual([p["reference"] for p in listed], [res.data["reference"]])
        # The cashbook was opened by the owner, but business money never shows in their personal history.
        self.assertEqual(self.as_user(self.owner).get("/api/v1/payments/").data["results"], [])
        self.assertEqual(self.as_user(self.outsider).get(self.url("external-payments/")).status_code, 404)


@override_settings(FLUXPAY_PAYMENT_PROVIDERS=RAILS)
class PersonalMpesaWithdrawalTests(BusinessTestCase):
    def withdraw(self, user, **body):
        wallet = personal_wallet(user)
        data = {"account_id": str(wallet.id), "amount": "200", "idempotency_key": "my-withdrawal-1", **body}
        with self.captureOnCommitCallbacks(execute=True):
            return self.as_user(user).post("/api/v1/withdrawals/mpesa/", data, format="json")

    def test_only_to_your_own_number(self):
        self.assertEqual(self.withdraw(self.outsider).data["error"]["code"], "phone_required")
        User.objects.filter(pk=self.outsider.pk).update(phone_number="0712345678")
        self.outsider.refresh_from_db()
        self.assertEqual(self.withdraw(self.outsider, phone_number="0799999999").status_code, 403)
        res = self.withdraw(self.outsider)
        self.assertEqual(res.status_code, 202, res.data)
        self.assertEqual(Account.objects.get(pk=personal_wallet(self.outsider).pk).balance, Decimal("800.00"))
        self.assertEqual(ExternalPayment.objects.get(id=res.data["id"]).metadata["mpesa_phone"], "+254712345678")
