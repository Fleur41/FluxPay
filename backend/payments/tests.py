import threading
from contextlib import nullcontext
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Sum
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APITestCase

from banking.models import Account, Transaction
from banking.services import open_wallet
from fluxpay.celery import app as celery_app
from fluxpay.exceptions import BusinessError

from . import services
from .models import ExternalPayment, WebhookEvent
from .providers.base import ProviderState, StatusResult

User = get_user_model()
Status = ExternalPayment.Status
FAKE = {"FAKE": "payments.providers.fake.FakeProvider"}
TOKEN = "test-webhook-token"
payment_settings = override_settings(
    FLUXPAY_SIGNUP_BONUS=Decimal("1000.00"), FLUXPAY_PAYMENT_PROVIDERS=FAKE, FLUXPAY_WEBHOOK_TOKEN=TOKEN
)


class PaymentTestMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Run queued tasks inline, whatever broker the environment configures. The app reads its config
        # with namespace="CELERY", so the CELERY_-prefixed keys win over task_always_eager & co.
        conf = celery_app.conf
        cls._celery_conf = (conf.task_always_eager, conf.task_eager_propagates)
        conf.update(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)

    @classmethod
    def tearDownClass(cls):
        eager, propagates = cls._celery_conf
        celery_app.conf.update(CELERY_TASK_ALWAYS_EAGER=eager, CELERY_TASK_EAGER_PROPAGATES=propagates)
        super().tearDownClass()

    def make_user(self, email="amina@example.com", name="Amina Wanjiru"):
        user = User.objects.create_user(email, "Str0ng-Pass!42", full_name=name)
        return user, open_wallet(user, currency="KES")

    def after_commit(self):
        # TestCase wraps each test in a transaction, so run on_commit work explicitly there.
        return self.captureOnCommitCallbacks(execute=True) if isinstance(self, TestCase) else nullcontext()

    def deposit(self, amount="500.00", key="dep-key-0001", **metadata):
        with self.after_commit():
            payment, _ = services.start_deposit(
                user=self.user,
                account_id=self.wallet.id,
                rail="FAKE",
                method=ExternalPayment.Method.FAKE_IN,
                amount=Decimal(amount),
                idempotency_key=key,
                metadata=metadata,
            )
        payment.refresh_from_db()
        return payment

    def payout(self, amount="300.00", key="out-key-0001", **metadata):
        with self.after_commit():
            payment, _ = services.start_payout(
                user=self.user,
                account_id=self.wallet.id,
                rail="FAKE",
                method=ExternalPayment.Method.FAKE_OUT,
                amount=Decimal(amount),
                idempotency_key=key,
                metadata=metadata,
            )
        payment.refresh_from_db()
        return payment

    def callback(self, payment, event_id="evt-1", token=TOKEN):
        with self.after_commit():
            return self.client.post(
                f"/hooks/fake/{token}/", {"event_id": event_id, "provider_ref": payment.provider_ref}, format="json"
            )

    def balance(self, account):
        account.refresh_from_db()
        return account.balance

    def assertLedgerBalanced(self):
        """All money in the system is the signup bonus: every deposit and payout nets to zero."""
        total = Account.objects.filter(currency="KES").aggregate(total=Sum("balance"))["total"]
        bonuses = Transaction.objects.filter(category=Transaction.Category.BONUS).aggregate(total=Sum("amount"))
        self.assertEqual(total, bonuses["total"])


@payment_settings
class DepositTests(PaymentTestMixin, APITestCase):
    def setUp(self):
        self.user, self.wallet = self.make_user()

    def test_deposit_is_submitted_then_credited_after_verified_callback(self):
        payment = self.deposit("500.00")
        self.assertEqual(payment.status, Status.PENDING)
        self.assertEqual(payment.provider_ref, f"FAKE-{payment.reference}")
        self.assertEqual(self.balance(self.wallet), Decimal("1000.00"))  # nothing credited before confirmation

        res = self.callback(payment)
        self.assertEqual(res.status_code, 200, res.data)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Status.COMPLETED)
        self.assertIsNotNone(payment.completed_at)
        self.assertEqual(self.balance(self.wallet), Decimal("1500.00"))
        clearing = services.clearing_account("FAKE", "KES")
        self.assertEqual(self.balance(clearing), Decimal("-500.00"))
        lines = Transaction.objects.filter(reference=payment.reference)
        self.assertEqual(
            sorted((line.account_id == self.wallet.id, line.type, line.category, line.status) for line in lines),
            [(False, "DEBIT", "DEPOSIT", "COMPLETED"), (True, "CREDIT", "DEPOSIT", "COMPLETED")],
        )
        self.assertIsNotNone(WebhookEvent.objects.get(event_id="evt-1").processed_at)
        self.assertLedgerBalanced()

    def test_replayed_callbacks_credit_once(self):
        payment = self.deposit("500.00")
        self.callback(payment, "evt-1")
        replay = self.callback(payment, "evt-1")
        self.assertTrue(replay.data["duplicate"])
        self.callback(payment, "evt-2")  # a second notification about the same payment
        self.assertEqual(self.balance(self.wallet), Decimal("1500.00"))
        self.assertEqual(Transaction.objects.filter(reference=payment.reference).count(), 2)

    def test_outcome_comes_from_provider_status_not_the_callback(self):
        payment = self.deposit("500.00", fake_outcome="failed")
        self.callback(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Status.FAILED)
        self.assertEqual(self.balance(self.wallet), Decimal("1000.00"))

    def test_amount_mismatch_is_flagged_and_not_credited(self):
        payment = self.deposit("500.00", fake_amount="5.00")
        self.callback(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Status.PENDING)
        self.assertTrue(payment.needs_review)
        self.assertIn("expected 500.00 KES", payment.review_note)
        self.assertEqual(self.balance(self.wallet), Decimal("1000.00"))

    def test_unknown_status_leaves_deposit_pending(self):
        payment = self.deposit("500.00", fake_outcome="unknown")
        payment = services.check_with_provider(payment.id)
        self.assertEqual(payment.status, Status.PENDING)

    def test_rejected_submission_fails_deposit(self):
        payment = self.deposit("500.00", fake_reject=True)
        self.assertEqual(payment.status, Status.FAILED)
        self.assertEqual(payment.failure_reason, "Rejected by the fake provider")

    def test_same_idempotency_key_returns_same_payment(self):
        first = self.deposit("500.00", key="same-key-123")
        second, created = services.start_deposit(
            user=self.user,
            account_id=self.wallet.id,
            rail="FAKE",
            method=ExternalPayment.Method.FAKE_IN,
            amount=Decimal("500.00"),
            idempotency_key="same-key-123",
        )
        self.assertFalse(created)
        self.assertEqual(first.id, second.id)

    def test_abandoned_deposit_expires_and_still_completes_if_paid_late(self):
        payment = self.deposit("500.00", fake_outcome="pending")
        payment = services.expire_if_abandoned(payment.id)
        self.assertEqual(payment.status, Status.EXPIRED)

        late = StatusResult(state=ProviderState.SUCCEEDED, amount=Decimal("500.00"), currency="KES")
        payment = services.settle_from_status(payment.id, late)
        self.assertEqual(payment.status, Status.COMPLETED)
        self.assertEqual(self.balance(self.wallet), Decimal("1500.00"))

    def test_success_after_failure_is_flagged_not_credited(self):
        payment = self.deposit("500.00", fake_outcome="failed")
        services.check_with_provider(payment.id)
        late = StatusResult(state=ProviderState.SUCCEEDED, amount=Decimal("500.00"), currency="KES")
        payment = services.settle_from_status(payment.id, late)
        self.assertEqual(payment.status, Status.FAILED)
        self.assertTrue(payment.needs_review)
        self.assertEqual(self.balance(self.wallet), Decimal("1000.00"))

    @override_settings(FLUXPAY_PAYMENT_PROVIDERS={})
    def test_unconfigured_rail_is_refused(self):
        with self.assertRaises(BusinessError) as ctx:
            self.deposit("500.00")
        self.assertEqual(ctx.exception.error_code, "rail_unavailable")
        self.assertFalse(ExternalPayment.objects.exists())


@payment_settings
class PayoutTests(PaymentTestMixin, TestCase):
    def setUp(self):
        self.user, self.wallet = self.make_user()

    def test_payout_holds_money_then_completes(self):
        payment = self.payout("300.00")
        self.assertEqual(payment.status, Status.SUBMITTED)
        self.assertEqual(self.balance(self.wallet), Decimal("700.00"))  # held as soon as it is created
        self.assertEqual(
            set(Transaction.objects.filter(reference=payment.reference).values_list("status", flat=True)), {"PENDING"}
        )

        payment = services.check_with_provider(payment.id)
        self.assertEqual(payment.status, Status.COMPLETED)
        self.assertEqual(self.balance(self.wallet), Decimal("700.00"))
        self.assertEqual(self.balance(services.clearing_account("FAKE", "KES")), Decimal("300.00"))
        self.assertEqual(
            set(Transaction.objects.filter(reference=payment.reference).values_list("status", flat=True)), {"COMPLETED"}
        )
        self.assertLedgerBalanced()

    def test_failed_payout_returns_the_money(self):
        payment = self.payout("300.00", fake_outcome="failed")
        payment = services.check_with_provider(payment.id)
        self.assertEqual(payment.status, Status.REVERSED)
        self.assertEqual(payment.failure_reason, "Declined by the fake provider")
        self.assertEqual(self.balance(self.wallet), Decimal("1000.00"))
        lines = Transaction.objects.filter(reference=payment.reference)
        self.assertEqual(lines.filter(category="WITHDRAWAL", status="FAILED").count(), 2)
        self.assertEqual(lines.filter(category="WITHDRAWAL_REVERSAL", status="COMPLETED").count(), 2)
        self.assertLedgerBalanced()

    def test_rejected_payout_submission_returns_the_money(self):
        payment = self.payout("300.00", fake_reject=True)
        self.assertEqual(payment.status, Status.REVERSED)
        self.assertEqual(self.balance(self.wallet), Decimal("1000.00"))

    def test_timeout_never_reverses(self):
        payment = self.payout("300.00", fake_outcome="unknown")
        payment = services.check_with_provider(payment.id)
        self.assertEqual(payment.status, Status.SUBMITTED)
        self.assertEqual(self.balance(self.wallet), Decimal("700.00"))

    def test_reversal_happens_once(self):
        payment = self.payout("300.00", fake_outcome="failed")
        services.check_with_provider(payment.id)
        services.fail_payment(payment.id, "failed again")
        self.assertEqual(self.balance(self.wallet), Decimal("1000.00"))

    def test_insufficient_funds_creates_nothing(self):
        with self.assertRaises(BusinessError) as ctx:
            self.payout("1000.01")
        self.assertEqual(ctx.exception.error_code, "insufficient_funds")
        self.assertFalse(ExternalPayment.objects.exists())
        self.assertEqual(self.balance(self.wallet), Decimal("1000.00"))

    def test_cannot_pay_out_from_someone_elses_wallet(self):
        other, other_wallet = self.make_user("brian@example.com", "Brian Otieno")
        with self.assertRaises(BusinessError) as ctx:
            services.start_payout(
                user=self.user,
                account_id=other_wallet.id,
                rail="FAKE",
                method=ExternalPayment.Method.FAKE_OUT,
                amount=Decimal("10.00"),
                idempotency_key="steal-key-01",
            )
        self.assertEqual(ctx.exception.error_code, "account_not_found")


@payment_settings
class WebhookTests(PaymentTestMixin, APITestCase):
    def setUp(self):
        self.user, self.wallet = self.make_user()

    def test_wrong_token_or_unknown_rail_is_not_found(self):
        payment = self.deposit()
        self.assertEqual(self.callback(payment, token="wrong").status_code, 404)
        res = self.client.post(f"/hooks/mpesa/{TOKEN}/", {"event_id": "e", "provider_ref": "x"}, format="json")
        self.assertEqual(res.status_code, 404)
        self.assertFalse(WebhookEvent.objects.exists())

    def test_malformed_callback_is_rejected_with_error_envelope(self):
        res = self.client.post(f"/hooks/fake/{TOKEN}/", {"provider_ref": "x"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"]["code"], "invalid_callback")
        self.assertFalse(WebhookEvent.objects.exists())

    def test_callback_for_unknown_payment_is_recorded_as_an_error(self):
        event = WebhookEvent.objects.create(
            rail="FAKE", event_id="evt-x", payload={"event_id": "evt-x", "provider_ref": "nope"}
        )
        with self.assertRaises(services.PaymentNotFound):
            services.process_webhook(event.id)
        services.give_up_on_webhook(event.id, "No payment with provider reference nope")
        event.refresh_from_db()
        self.assertIsNotNone(event.processed_at)
        self.assertIn("nope", event.error)


@payment_settings
class PaymentApiTests(PaymentTestMixin, APITestCase):
    def setUp(self):
        self.user, self.wallet = self.make_user()

    def test_lists_only_own_payments(self):
        mine = self.deposit()
        other, other_wallet = self.make_user("brian@example.com", "Brian Otieno")
        services.start_deposit(
            user=other,
            account_id=other_wallet.id,
            rail="FAKE",
            method=ExternalPayment.Method.FAKE_IN,
            amount=Decimal("10.00"),
            idempotency_key="brian-key-01",
        )
        self.client.force_authenticate(self.user)
        res = self.client.get("/api/v1/payments/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual([p["id"] for p in res.data["results"]], [str(mine.id)])
        self.assertEqual(res.data["results"][0]["status"], "PENDING")
        detail = self.client.get(f"/api/v1/payments/{mine.id}/")
        self.assertEqual(detail.data["reference"], mine.reference)

    def test_clearing_accounts_cannot_be_looked_up_or_paid(self):
        clearing = services.clearing_account("FAKE", "KES")
        self.client.force_authenticate(self.user)
        res = self.client.get("/api/v1/accounts/lookup/", {"account_number": clearing.account_number})
        self.assertEqual(res.status_code, 404)
        res = self.client.post(
            "/api/v1/transfers/",
            {
                "source_account_id": str(self.wallet.id),
                "destination_account_number": clearing.account_number,
                "amount": "10.00",
                "idempotency_key": "to-clearing-1",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self.balance(self.wallet), Decimal("1000.00"))


@payment_settings
@skipUnless(connection.vendor == "postgresql", "needs real row locks (PostgreSQL)")
class ConcurrencyTests(PaymentTestMixin, TransactionTestCase):
    def test_racing_settlements_credit_once(self):
        self.user, self.wallet = self.make_user()
        payment = self.deposit("500.00")
        result = StatusResult(state=ProviderState.SUCCEEDED, amount=Decimal("500.00"), currency="KES")
        barrier = threading.Barrier(4)
        errors = []

        def settle():
            try:
                barrier.wait()
                services.settle_from_status(payment.id, result)
            except Exception as exc:  # surfaced below
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=settle) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(self.balance(self.wallet), Decimal("1500.00"))
        self.assertEqual(Transaction.objects.filter(reference=payment.reference).count(), 2)
