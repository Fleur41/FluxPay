from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.db.models import Sum
from django.test import TestCase, override_settings

from audit.models import AuditEvent
from fluxpay.celery import app as celery_app
from fluxpay.exceptions import BusinessError
from fluxpay.testing import customer_deposit
from notifications.models import Notification
from organizations import services as org_services
from platform_settings.models import Currency

from .models import Account, ManualAdjustment, Transaction
from .services import open_wallet, post_adjustment, system_account

User = get_user_model()
PASSWORD = "Str0ng-Pass!42"
REASON = "Cash deposited at the Nairobi office, receipt 1042"


class AdjustmentServiceTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("ops@fluxpay.test", PASSWORD, full_name="Opal Ops", is_staff=True)
        self.customer = User.objects.create_user("simon@example.com", PASSWORD, full_name="Simon Kip")
        self.wallet = open_wallet(self.customer)
        self.receipt = customer_deposit("5000.00")

    def credit(self, amount="500.00", **kwargs):
        return post_adjustment(staff=self.staff, account_id=self.wallet.id, kind="CREDIT", amount=Decimal(amount),
                               reason=kwargs.get("reason", REASON), cashbook_entry=self.receipt)

    def test_top_up_moves_money_from_the_adjustments_account(self):
        adjustment = self.credit("500.00")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("500.00"))
        self.assertEqual(adjustment.balance_after, Decimal("500.00"))
        pool = Account.objects.get(system_key="adjustments:KES")
        self.assertEqual(pool.balance, Decimal("-500.00"))
        self.assertEqual(Account.objects.aggregate(total=Sum("balance"))["total"], Decimal("0.00"))
        line = Transaction.objects.get(account=self.wallet)
        self.assertEqual(
            (line.type, line.category, line.description, line.counterparty_name),
            ("CREDIT", "ADJUSTMENT", "Top-up by FluxPay", "FluxPay"),
        )

    def test_correction_takes_money_back_but_never_below_zero(self):
        self.credit("500.00")
        post_adjustment(staff=self.staff, account_id=self.wallet.id, kind="DEBIT", amount=Decimal("200.00"),
                        reason="Duplicate top-up on 4 Oct, reversing part of it", cashbook_entry=self.receipt)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("300.00"))
        with self.assertRaises(BusinessError) as ctx:
            post_adjustment(staff=self.staff, account_id=self.wallet.id, kind="DEBIT", amount=Decimal("300.01"),
                            reason="Trying to take more than the wallet holds", cashbook_entry=self.receipt)
        self.assertEqual(ctx.exception.error_code, "insufficient_funds")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("300.00"))

    def test_reason_is_required(self):
        with self.assertRaises(BusinessError) as ctx:
            self.credit(reason="cash")
        self.assertEqual(ctx.exception.error_code, "reason_required")
        self.assertFalse(ManualAdjustment.objects.exists())

    def test_currency_limits_guard_against_typos(self):
        Currency.objects.filter(code="KES").update(max_transfer=Decimal("100000.00"))
        with self.assertRaises(BusinessError) as ctx:
            self.credit("1000000.00")  # one zero too many
        self.assertEqual(ctx.exception.error_code, "limit_exceeded")

    def test_system_accounts_cannot_be_adjusted(self):
        pool = system_account("adjustments:KES", "Manual adjustments KES", "KES")
        with self.assertRaises(BusinessError):
            post_adjustment(staff=self.staff, account_id=pool.id, kind="CREDIT", amount=Decimal("10"), reason=REASON,
                            cashbook_entry=self.receipt)

    def test_business_wallets_can_be_topped_up(self):
        org = org_services.create_organization(user=self.customer, name="Kip Traders")
        business = org.accounts.get()
        post_adjustment(staff=self.staff, account_id=business.id, kind="CREDIT", amount=Decimal("1000"), reason=REASON,
                        cashbook_entry=self.receipt)
        business.refresh_from_db()
        self.assertEqual(business.balance, Decimal("1000.00"))

    def test_it_is_audited_with_the_reason(self):
        adjustment = self.credit("500.00")
        event = AuditEvent.objects.get(action="adjustment.credited")
        self.assertEqual(event.actor, self.staff)
        self.assertEqual(event.target_id, str(adjustment.id))
        self.assertEqual(event.metadata["reason"], REASON)
        self.assertEqual(event.metadata["amount"], "500.00")


@override_settings(FLUXPAY_SMS_BACKEND="notifications.tests.RecordingSmsBackend")
class AdjustmentAlertTests(TestCase):
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

    def test_customer_is_told_by_email_and_sms(self):
        staff = User.objects.create_user("ops@fluxpay.test", PASSWORD, full_name="Opal Ops", is_staff=True)
        customer = User.objects.create_user("simon@example.com", PASSWORD, full_name="Simon Kip", phone_number="0711000222")
        wallet = open_wallet(customer)
        with self.captureOnCommitCallbacks(execute=True):
            post_adjustment(staff=staff, account_id=wallet.id, kind="CREDIT", amount=Decimal("750.00"), reason=REASON,
                            cashbook_entry=customer_deposit("750.00"))
        self.assertEqual([m.subject for m in mail.outbox], ["FluxPay added KES 750.00 to your wallet"])
        self.assertIn("New balance: KES 750.00", mail.outbox[0].body)
        self.assertNotIn(REASON, mail.outbox[0].body)  # the internal reason stays internal
        self.assertEqual(
            set(Notification.objects.values_list("channel", "status")), {("EMAIL", "SENT"), ("SMS", "SENT")}
        )


class AdjustmentAdminTests(TestCase):
    URL = "/admin/banking/manualadjustment/"

    def setUp(self):
        self.customer = User.objects.create_user("simon@example.com", PASSWORD, full_name="Simon Kip")
        self.wallet = open_wallet(self.customer)
        self.staff = User.objects.create_user("ops@fluxpay.test", PASSWORD, full_name="Opal Ops", is_staff=True)
        self.receipt = customer_deposit("5000.00")

    def grant(self):
        self.staff.user_permissions.add(Permission.objects.get(codename="post_adjustment"))

    def post(self, **fields):
        data = {
            "cashbook_entry": str(self.receipt.pk),
            "account": str(self.wallet.id),
            "kind": "CREDIT",
            "amount": "500.00",
            "reason": REASON,
            **fields,
        }
        return self.client.post(self.URL + "add/", data)

    def test_staff_need_the_permission(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.URL + "add/").status_code, 403)
        self.assertEqual(self.post().status_code, 403)
        self.assertFalse(ManualAdjustment.objects.exists())

    def test_permitted_staff_top_up_through_admin(self):
        self.grant()
        self.client.force_login(self.staff)
        res = self.post()
        self.assertEqual(res.status_code, 302, res.context and res.context["adminform"].form.errors)
        adjustment = ManualAdjustment.objects.get()
        self.assertEqual((adjustment.created_by, adjustment.amount), (self.staff, Decimal("500.00")))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("500.00"))
        self.assertTrue(adjustment.reference.startswith("FP"))

    def test_mistakes_show_as_form_errors(self):
        self.grant()
        self.client.force_login(self.staff)
        res = self.post(kind="DEBIT", amount="10.00")  # the wallet is empty
        self.assertEqual(res.status_code, 200)
        self.assertIn("The wallet only holds 0.00 KES.", str(res.context["adminform"].form.errors))
        res = self.post(reason="cash")
        self.assertIn("at least 10 characters", str(res.context["adminform"].form.errors))
        self.assertFalse(ManualAdjustment.objects.exists())

    def test_posted_adjustments_cannot_be_changed_or_deleted(self):
        self.grant()
        self.client.force_login(self.staff)
        self.post()
        adjustment = ManualAdjustment.objects.get()
        page = self.client.get(f"{self.URL}{adjustment.pk}/change/")
        self.assertEqual(page.status_code, 200)  # viewable
        self.assertNotContains(page, 'name="_save"')  # but no save button
        self.assertEqual(self.client.post(f"{self.URL}{adjustment.pk}/delete/", {"post": "yes"}).status_code, 403)
