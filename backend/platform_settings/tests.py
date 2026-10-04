from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from audit.models import AuditEvent
from banking.models import Account, Transaction
from banking.services import open_wallet, transfer_funds
from fluxpay.exceptions import BusinessError
from organizations import services as org_services
from organizations.models import Invitation, Membership

from .models import Currency, PlatformSettings

User = get_user_model()
PASSWORD = "Str0ng-Pass!42"


def make_user(email, name="Test User"):
    return User.objects.create_user(email, PASSWORD, full_name=name)


class MoneyComesFromSomewhereTests(TestCase):
    def test_new_wallets_start_empty_unless_staff_set_a_bonus(self):
        wallet = open_wallet(make_user("a@example.com"))
        self.assertEqual(wallet.balance, Decimal("0.00"))
        self.assertFalse(Transaction.objects.exists())

    def test_a_bonus_comes_from_the_promotions_account(self):
        Currency.objects.filter(code="KES").update(signup_bonus=Decimal("250.00"))
        wallet = open_wallet(make_user("a@example.com"))
        open_wallet(make_user("b@example.com"))
        self.assertEqual(wallet.balance, Decimal("250.00"))
        promotions = Account.objects.get(system_key="promotions:KES")
        self.assertEqual(promotions.balance, Decimal("-500.00"))
        self.assertEqual(Account.objects.aggregate(total=Sum("balance"))["total"], Decimal("0.00"))
        line = Transaction.objects.get(account=wallet)
        self.assertEqual((line.type, line.category, line.counterparty_name), ("CREDIT", "BONUS", "FluxPay"))

    def test_the_bonus_is_per_currency(self):
        Currency.objects.filter(code="KES").update(signup_bonus=Decimal("1000.00"))
        usd_wallet = open_wallet(make_user("a@example.com"), currency="USD")
        self.assertEqual(usd_wallet.balance, Decimal("0.00"))

    def test_new_wallets_use_the_configured_default_currency(self):
        PlatformSettings.objects.update(default_currency_id="USD")
        self.assertEqual(open_wallet(make_user("a@example.com")).currency, "USD")

    def test_disabled_currencies_cannot_be_opened(self):
        Currency.objects.filter(code="GBP").update(enabled=False)
        with self.assertRaises(BusinessError) as ctx:
            open_wallet(make_user("a@example.com"), currency="GBP")
        self.assertEqual(ctx.exception.error_code, "currency_not_supported")


class LimitTests(APITestCase):
    def setUp(self):
        Currency.objects.filter(code="KES").update(
            signup_bonus=Decimal("10000.00"), min_transfer=Decimal("10.00"), max_transfer=Decimal("2000.00")
        )
        self.alice, self.bob = make_user("alice@example.com"), make_user("bob@example.com")
        self.a_acc, self.b_acc = open_wallet(self.alice), open_wallet(self.bob)
        self.client.force_authenticate(self.alice)

    def send(self, amount, key):
        return self.client.post(
            "/api/v1/transfers/",
            {"source_account_id": str(self.a_acc.id), "destination_account_number": self.b_acc.account_number,
             "amount": amount, "idempotency_key": key},
            format="json",
        )

    def test_limits_come_from_the_currency(self):
        too_small = self.send("9.99", "limit-key-1")
        self.assertEqual(too_small.data["error"]["code"], "amount_too_small")
        self.assertIn("10.00 KES", too_small.data["error"]["message"])
        too_big = self.send("2000.01", "limit-key-2")
        self.assertEqual(too_big.data["error"]["code"], "limit_exceeded")
        self.assertEqual(self.send("2000.00", "limit-key-3").status_code, 201)

    def test_staff_changes_apply_at_once(self):
        Currency.objects.filter(code="KES").update(max_transfer=Decimal("5000.00"))
        self.assertEqual(self.send("4000.00", "limit-key-4").status_code, 201)

    def test_business_payments_follow_the_same_limits(self):
        org = org_services.create_organization(user=self.alice, name="Acme")
        transfer_funds(user=self.alice, source_id=self.a_acc.id, destination_number=org.accounts.get().account_number,
                       amount=Decimal("2000.00"), note="", idempotency_key="fund-org-1")
        membership = Membership.objects.get(organization=org, user=self.alice)
        with self.assertRaises(BusinessError) as ctx:
            org_services.create_payment_request(
                membership=membership, source_account_id=org.accounts.get().id,
                destination_account_number=self.b_acc.account_number, amount=Decimal("5.00"), note="",
                idempotency_key="org-small-1",
            )
        self.assertEqual(ctx.exception.error_code, "amount_too_small")


class OtherRulesTests(APITestCase):
    def test_invitation_expiry_comes_from_settings(self):
        PlatformSettings.objects.update(invitation_expiry_days=2)
        owner = make_user("owner@example.com", "Olivia Owner")
        open_wallet(owner)
        org = org_services.create_organization(user=owner, name="Acme")
        membership = Membership.objects.get(organization=org, user=owner)
        invitation, _ = org_services.invite_member(membership=membership, email="new@example.com", role="VIEWER")
        self.assertAlmostEqual(
            invitation.expires_at, timezone.now() + timedelta(days=2), delta=timedelta(seconds=30)
        )
        self.assertEqual(Invitation.objects.count(), 1)

    def test_statement_range_comes_from_settings(self):
        PlatformSettings.objects.update(statement_max_days=31)
        user = make_user("amina@example.com")
        open_wallet(user)
        self.client.force_authenticate(user)
        ok = self.client.get("/api/v1/statements/", {"date_from": "2026-09-01", "date_to": "2026-10-01"})
        self.assertEqual(ok.status_code, 200)
        too_long = self.client.get("/api/v1/statements/", {"date_from": "2026-09-01", "date_to": "2026-10-02"})
        self.assertEqual(too_long.status_code, 400)
        self.assertIn("at most 31 days", too_long.data["error"]["message"])

    def test_sign_up_accepts_only_enabled_currencies(self):
        Currency.objects.filter(code="EUR").update(enabled=False)
        res = self.client.post(
            "/api/v1/auth/register/",
            {"email": "new@example.com", "full_name": "New Person", "password": PASSWORD, "currency": "EUR"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            "/api/v1/auth/register/",
            {"email": "new@example.com", "full_name": "New Person", "password": PASSWORD, "currency": "usd"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(User.objects.get(email="new@example.com").accounts.get().currency, "USD")


class ConfigApiTests(APITestCase):
    def test_public_config_reflects_the_database(self):
        Currency.objects.filter(code="GBP").update(enabled=False)
        Currency.objects.filter(code="KES").update(max_transfer=Decimal("750000.00"))
        PlatformSettings.objects.update(session_timeout_minutes=10, budget_needs_percent=60, budget_wants_percent=20)
        res = self.client.get("/api/v1/config/")  # no login: the sign-up screen needs it
        self.assertEqual(res.status_code, 200)
        self.assertEqual([c["code"] for c in res.data["currencies"]], ["KES", "USD", "EUR"])
        self.assertEqual(res.data["currencies"][0]["max_transfer"], "750000.00")
        self.assertEqual(res.data["default_currency"], "KES")
        self.assertEqual(res.data["session_timeout_minutes"], 10)
        self.assertEqual(res.data["budget_guideline"], {"needs": 60, "wants": 20, "savings": 20})
        self.assertNotIn("signup_bonus", res.data["currencies"][0])  # promotions are not advertised


class ValidationTests(TestCase):
    def test_budget_guideline_must_add_up_to_100(self):
        settings_row = PlatformSettings.objects.get()
        settings_row.budget_needs_percent = 70
        with self.assertRaisesMessage(ValidationError, "add up to 100%"):
            settings_row.full_clean()

    def test_default_currency_must_be_enabled(self):
        Currency.objects.filter(code="KES").update(enabled=False)
        with self.assertRaises(ValidationError):
            PlatformSettings.objects.get().full_clean()

    def test_currency_max_must_be_at_least_min(self):
        kes = Currency.objects.get(code="KES")
        kes.min_transfer, kes.max_transfer = Decimal("100.00"), Decimal("50.00")
        with self.assertRaises(ValidationError):
            kes.full_clean()


class AdminAuditTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser("admin@example.com", PASSWORD, full_name="Ada Admin")
        self.client.force_login(self.staff)

    def test_changing_a_currency_in_admin_is_audited(self):
        kes = Currency.objects.get(code="KES")
        res = self.client.post(
            "/admin/platform_settings/currency/KES/change/",
            {"name": kes.name, "enabled": "on", "sort_order": 0, "min_transfer": "5.00", "max_transfer": "100000.00",
             "signup_bonus": "0.00"},
        )
        self.assertEqual(res.status_code, 302, getattr(res, "context", None) and res.context["adminform"].form.errors)
        kes.refresh_from_db()
        self.assertEqual(kes.max_transfer, Decimal("100000.00"))
        event = AuditEvent.objects.get(action="config.currency_changed")
        self.assertEqual(event.actor, self.staff)
        self.assertEqual(event.metadata["changes"]["max_transfer"], {"from": "500000.00", "to": "100000.00"})

    def test_platform_settings_cannot_be_added_or_deleted(self):
        self.assertEqual(self.client.get("/admin/platform_settings/platformsettings/add/").status_code, 403)
        self.assertEqual(self.client.get("/admin/platform_settings/platformsettings/1/delete/").status_code, 403)
