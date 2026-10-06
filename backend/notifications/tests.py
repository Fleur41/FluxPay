from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, TransactionTestCase, override_settings
from kombu.exceptions import OperationalError
from rest_framework.test import APIClient, APITestCase

from banking.services import open_wallet, transfer_funds
from fluxpay.celery import app as celery_app
from fluxpay.testing import funded
from organizations import services as org_services
from organizations.models import Membership
from payments import services as payment_services
from payments.models import ExternalPayment

from . import services
from .models import Notification, NotificationSettings
from .sms import SmsError, normalize_phone

User = get_user_model()


class RecordingSmsBackend:
    sent: list = []

    def send(self, to, message):
        RecordingSmsBackend.sent.append((to, message))
        return f"msg-{len(RecordingSmsBackend.sent)}"


class FailingSmsBackend:
    def send(self, to, message):
        raise SmsError("gateway down")


@funded
@override_settings(
    FLUXPAY_SMS_BACKEND="notifications.tests.RecordingSmsBackend",
    FLUXPAY_PAYMENT_PROVIDERS={"FAKE": "payments.providers.fake.FakeProvider"},
)
class AlertTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        conf = celery_app.conf
        cls._eager = (conf.task_always_eager, conf.task_eager_propagates)
        conf.update(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)

    @classmethod
    def tearDownClass(cls):
        eager, propagates = cls._eager
        celery_app.conf.update(CELERY_TASK_ALWAYS_EAGER=eager, CELERY_TASK_EAGER_PROPAGATES=propagates)
        super().tearDownClass()

    def setUp(self):
        RecordingSmsBackend.sent = []
        self.amina = self.make_user("amina@example.com", "Amina Wanjiru", "+254700000001")
        self.brian = self.make_user("brian@example.com", "Brian Otieno", "0712 345 678")

    def make_user(self, email, name, phone=""):
        user = User.objects.create_user(email, "Str0ng-Pass!42", full_name=name, phone_number=phone)
        open_wallet(user)
        return user

    def wallet(self, user):
        return user.accounts.get(organization__isnull=True)

    def send(self, sender, recipient_account, amount="200.00", key="alert-transfer-1", note=""):
        with self.captureOnCommitCallbacks(execute=True):
            transfer, _, _ = transfer_funds(
                user=sender,
                source_id=self.wallet(sender).id,
                destination_number=recipient_account.account_number,
                amount=Decimal(amount),
                note=note,
                idempotency_key=key,
            )
        return transfer


class TransferAlertTests(AlertTestCase):
    def test_both_sides_get_email_and_sms(self):
        transfer = self.send(self.amina, self.wallet(self.brian), note="Lunch")

        subjects = sorted(m.subject for m in mail.outbox)
        self.assertEqual(subjects, ["You received KES 200.00 from Amina Wanjiru", "You sent KES 200.00 to Brian Otieno"])
        sent_mail = next(m for m in mail.outbox if m.to == ["amina@example.com"])
        self.assertIn(f"Reference: {transfer.reference}", sent_mail.body)
        self.assertIn("New balance: KES 800.00", sent_mail.body)
        self.assertIn('Note: "Lunch"', sent_mail.body)
        self.assertNotIn(self.wallet(self.brian).account_number, sent_mail.body)  # only the last 4 digits

        sms = dict(RecordingSmsBackend.sent)
        self.assertEqual(set(sms), {"+254700000001", "+254712345678"})  # Brian's local number normalised
        self.assertIn(f"Ref {transfer.reference}", sms["+254700000001"])
        self.assertIn("Bal KES 1,200.00", sms["+254712345678"])
        self.assertTrue(all(len(text) <= 160 for text in sms.values()), sms)

        self.assertEqual(Notification.objects.filter(status=Notification.Status.SENT).count(), 4)
        self.assertEqual(Notification.objects.get(user=self.brian, channel="SMS").provider_message_id[:4], "msg-")

    def test_turned_off_channels_are_skipped(self):
        NotificationSettings.objects.create(user=self.brian, email_enabled=True, sms_enabled=False)
        self.send(self.amina, self.wallet(self.brian))
        self.assertEqual([to for to, _ in RecordingSmsBackend.sent], ["+254700000001"])
        self.assertEqual(len(mail.outbox), 2)

    def test_no_usable_phone_means_email_only(self):
        carol = self.make_user("carol@example.com", "Carol Kim", "not-a-number")
        self.send(self.amina, self.wallet(carol))
        self.assertFalse(Notification.objects.filter(user=carol, channel="SMS").exists())
        self.assertTrue(Notification.objects.filter(user=carol, channel="EMAIL").exists())

    def test_rerunning_the_alert_job_never_alerts_twice(self):
        transfer = self.send(self.amina, self.wallet(self.brian))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(services.alert_transfer(transfer.id), [])
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(len(RecordingSmsBackend.sent), 2)

    @override_settings(FLUXPAY_SMS_BACKEND="notifications.tests.FailingSmsBackend")
    def test_failing_sms_is_retried_then_marked_failed(self):
        transfer, _, _ = transfer_funds(  # on_commit work not run: alerts are created and delivered by hand
            user=self.amina,
            source_id=self.wallet(self.amina).id,
            destination_number=self.wallet(self.brian).account_number,
            amount=Decimal("5.00"),
            note="",
            idempotency_key="failing-sms-1",
        )
        services.alert_transfer(transfer.id)
        sms = Notification.objects.get(user=self.amina, channel="SMS")
        for attempt in range(1, services.MAX_ATTEMPTS):
            with self.assertRaises(SmsError):
                services.deliver(sms.id)
            sms.refresh_from_db()
            self.assertEqual((sms.attempts, sms.status), (attempt, Notification.Status.QUEUED))
        services.deliver(sms.id)  # the last attempt gives up instead of raising
        sms.refresh_from_db()
        self.assertEqual(sms.status, Notification.Status.FAILED)
        self.assertIn("gateway down", sms.error)


class BusinessAndPaymentAlertTests(AlertTestCase):
    def test_business_wallet_alerts_go_to_owners_and_admins(self):
        org = org_services.create_organization(user=self.amina, name="Acme Ltd")
        admin = self.make_user("adam@example.com", "Adam Admin", "+254711111111")
        finance = self.make_user("fiona@example.com", "Fiona Finance", "+254722222222")
        Membership.objects.create(organization=org, user=admin, role=Membership.Role.ADMIN)
        Membership.objects.create(organization=org, user=finance, role=Membership.Role.FINANCE)

        self.send(self.brian, org.accounts.get(), amount="300.00", key="pay-business-1")
        received = sorted(m.to[0] for m in mail.outbox if "received" in m.subject)
        self.assertEqual(received, ["adam@example.com", "amina@example.com"])  # not finance
        self.assertIn("Acme Ltd received KES 300.00 from Brian Otieno", [m.subject for m in mail.outbox])

    def test_payout_reversal_and_deposit_alerts(self):
        with self.captureOnCommitCallbacks(execute=True):
            payout, _ = payment_services.start_payout(
                user=self.amina, account_id=self.wallet(self.amina).id, rail="FAKE",
                method=ExternalPayment.Method.FAKE_OUT, amount=Decimal("40.00"), idempotency_key="alert-payout-1",
                metadata={"fake_outcome": "failed"},
            )
        with self.captureOnCommitCallbacks(execute=True):
            payment_services.check_with_provider(payout.id)
        with self.captureOnCommitCallbacks(execute=True):
            deposit, _ = payment_services.start_deposit(
                user=self.amina, account_id=self.wallet(self.amina).id, rail="FAKE",
                method=ExternalPayment.Method.FAKE_IN, amount=Decimal("25.00"), idempotency_key="alert-deposit-1",
            )
        with self.captureOnCommitCallbacks(execute=True):
            payment_services.check_with_provider(deposit.id)

        subjects = [m.subject for m in mail.outbox]
        self.assertIn("Your KES 40.00 Fake (tests only) payout failed: money returned", subjects)
        self.assertIn("You added KES 25.00 from Fake (tests only)", subjects)
        reversal = next(m for m in mail.outbox if "payout failed" in m.subject)
        self.assertIn("New balance: KES 1,000.00", reversal.body)


class NotificationSettingsApiTests(APITestCase):
    def test_defaults_on_and_can_be_changed(self):
        user = User.objects.create_user("amina@example.com", "Str0ng-Pass!42", full_name="Amina Wanjiru")
        self.client.force_authenticate(user)
        res = self.client.get("/api/v1/notifications/settings/")
        self.assertEqual(res.data, {"email_enabled": True, "sms_enabled": True})
        res = self.client.patch("/api/v1/notifications/settings/", {"sms_enabled": False}, format="json")
        self.assertEqual(res.data, {"email_enabled": True, "sms_enabled": False})
        self.assertFalse(NotificationSettings.objects.get(user=user).sms_enabled)

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/v1/notifications/settings/").status_code, 401)


class PhoneNumberTests(TestCase):
    def test_normalize(self):
        cases = {
            "0712345678": "+254712345678",
            "0712 345 678": "+254712345678",
            "712345678": "+254712345678",
            "254112345678": "+254112345678",
            "+254712345678": "+254712345678",
            "+1 (202) 555-0100": "+12025550100",
            "": None,
            "12345": None,
            "0812345678": None,
            "+0123": None,
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_phone(raw), expected, raw)


@funded
class BrokerOutageTests(TransactionTestCase):
    """Real commits, so on_commit runs as in production."""

    serialized_rollback = True  # keep the platform settings rows the data migration created

    def test_transfer_succeeds_when_alerts_cannot_be_queued(self):
        amina = User.objects.create_user("amina@example.com", "Str0ng-Pass!42", full_name="Amina Wanjiru")
        brian = User.objects.create_user("brian@example.com", "Str0ng-Pass!42", full_name="Brian Otieno")
        wallet, brian_wallet = open_wallet(amina), open_wallet(brian)
        client = APIClient()
        client.force_authenticate(amina)
        with mock.patch("notifications.tasks.alert_transfer_task.delay", side_effect=OperationalError("broker down")):
            res = client.post(
                "/api/v1/transfers/",
                {"source_account_id": str(wallet.id), "destination_account_number": brian_wallet.account_number,
                 "amount": "50.00", "idempotency_key": "outage-transfer-1"},
                format="json",
            )
        self.assertEqual(res.status_code, 201, res.data)  # the money moved; a lost alert must not hide that
        brian_wallet.refresh_from_db()
        self.assertEqual(brian_wallet.balance, Decimal("1050.00"))


class EmailDeliveryTests(TestCase):
    """Real SMTP for real addresses; reserved test domains are only printed, so seed data never bounces."""

    def test_test_addresses_are_printed_not_sent(self):
        from unittest import mock

        from django.core.mail import EmailMessage

        from notifications.email import SmtpExceptTestAddressesBackend, deliverable

        self.assertFalse(deliverable("worker001@kamautraders.test"))
        self.assertFalse(deliverable("someone@example.com"))
        self.assertTrue(deliverable("person@gmail.com"))
        backend = SmtpExceptTestAddressesBackend(host="smtp.invalid", fail_silently=False)
        with mock.patch("django.core.mail.backends.smtp.EmailBackend.send_messages", return_value=1) as smtp, \
             mock.patch("django.core.mail.backends.console.EmailBackend.send_messages", return_value=1) as console:  # fmt: skip
            sent = backend.send_messages([
                EmailMessage("a", "b", to=["worker001@kamautraders.test"]),
                EmailMessage("a", "b", to=["person@gmail.com", "x@example.com"]),
            ])  # fmt: skip
        self.assertEqual(sent, 2)
        self.assertEqual([m.to for m in smtp.call_args.args[0]], [["person@gmail.com"]])
        self.assertEqual([m.to for m in console.call_args.args[0]], [["worker001@kamautraders.test"]])
