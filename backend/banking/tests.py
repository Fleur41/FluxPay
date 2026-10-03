from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase

from banking.models import Transaction
from banking.services import open_wallet

User = get_user_model()
PASSWORD = "Str0ng-Pass!42"


@override_settings(FLUXPAY_SIGNUP_BONUS=Decimal("1000.00"))
class AuthFlowTests(APITestCase):
    def test_register_returns_tokens_and_opens_wallet_with_bonus(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {"email": "Jane@Example.com", "full_name": "Jane Doe", "password": PASSWORD, "currency": "KES"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIn("access", res.data)
        self.assertEqual(res.data["user"]["email"], "jane@example.com")

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        accounts = self.client.get("/api/v1/accounts/").data
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["balance"], "1000.00")
        self.assertEqual(accounts[0]["currency"], "KES")

    def test_login_is_case_insensitive_and_returns_profile(self):
        User.objects.create_user("jane@example.com", PASSWORD, full_name="Jane Doe")
        res = self.client.post("/api/v1/auth/login/", {"email": "JANE@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["user"]["full_name"], "Jane Doe")

    def test_errors_use_envelope(self):
        res = self.client.post("/api/v1/auth/login/", {"email": "nobody@example.com", "password": "x"}, format="json")
        self.assertEqual(res.status_code, 401)
        self.assertIn("error", res.data)
        self.assertIn("message", res.data["error"])

    def test_refresh_rotates_and_logout_blacklists(self):
        User.objects.create_user("jane@example.com", PASSWORD, full_name="Jane Doe")
        tokens = self.client.post("/api/v1/auth/login/", {"email": "jane@example.com", "password": PASSWORD}, format="json").data
        refreshed = self.client.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn("refresh", refreshed.data)
        # Old refresh token is blacklisted after rotation.
        again = self.client.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(again.status_code, 401)

    def test_password_reset_round_trip(self):
        User.objects.create_user("jane@example.com", PASSWORD, full_name="Jane Doe")
        res = self.client.post("/api/v1/auth/password-reset/", {"email": "jane@example.com"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        link = next(line for line in mail.outbox[0].body.splitlines() if line.startswith("fluxpay://"))
        query = dict(part.split("=", 1) for part in link.split("?", 1)[1].split("&"))
        confirm = self.client.post(
            "/api/v1/auth/password-reset/confirm/",
            {"uid": query["uid"], "token": query["token"], "new_password": "Brand-New-Pass#9"},
            format="json",
        )
        self.assertEqual(confirm.status_code, 200, confirm.data)
        self.assertTrue(User.objects.get(email="jane@example.com").check_password("Brand-New-Pass#9"))

    def test_unknown_email_reset_does_not_leak(self):
        res = self.client.post("/api/v1/auth/password-reset/", {"email": "ghost@example.com"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(FLUXPAY_SIGNUP_BONUS=Decimal("1000.00"), FLUXPAY_MAX_TRANSFER=Decimal("5000.00"))
class TransferTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice@example.com", PASSWORD, full_name="Alice Kamau")
        self.bob = User.objects.create_user("bob@example.com", PASSWORD, full_name="Bob Mwangi")
        self.a_acc = open_wallet(self.alice, "KES")
        self.b_acc = open_wallet(self.bob, "KES")
        self.client.force_authenticate(self.alice)

    def send(self, amount="250.00", key="key-00000001", to=None, source=None):
        return self.client.post(
            "/api/v1/transfers/",
            {
                "source_account_id": str(source or self.a_acc.id),
                "destination_account_number": to or self.b_acc.account_number,
                "amount": amount,
                "note": "Dinner",
                "idempotency_key": key,
            },
            format="json",
        )

    def test_transfer_moves_money_and_writes_both_ledger_lines(self):
        res = self.send()
        self.assertEqual(res.status_code, 201, res.data)
        self.a_acc.refresh_from_db()
        self.b_acc.refresh_from_db()
        self.assertEqual(self.a_acc.balance, Decimal("750.00"))
        self.assertEqual(self.b_acc.balance, Decimal("1250.00"))
        reference = res.data["transfer"]["reference"]
        self.assertEqual(Transaction.objects.filter(reference=reference).count(), 2)
        self.assertEqual(res.data["transaction"]["type"], "DEBIT")
        self.assertEqual(res.data["transaction"]["balance_after"], "750.00")

    def test_same_idempotency_key_does_not_double_charge(self):
        first = self.send(key="retry-key-123")
        second = self.send(key="retry-key-123")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["transfer"]["id"], second.data["transfer"]["id"])
        self.a_acc.refresh_from_db()
        self.assertEqual(self.a_acc.balance, Decimal("750.00"))

    def test_insufficient_funds(self):
        res = self.send(amount="1000.01")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"]["code"], "insufficient_funds")

    def test_limit(self):
        res = self.send(amount="5000.01")
        self.assertEqual(res.data["error"]["code"], "limit_exceeded")

    def test_cannot_spend_from_someone_elses_account(self):
        res = self.send(source=self.b_acc.id, to=self.a_acc.account_number)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.data["error"]["code"], "account_not_found")

    def test_same_account_rejected(self):
        res = self.send(to=self.a_acc.account_number)
        self.assertEqual(res.data["error"]["code"], "same_account")

    def test_currency_mismatch_rejected(self):
        usd = open_wallet(self.bob, "USD", name="Dollar wallet")
        res = self.send(to=usd.account_number)
        self.assertEqual(res.data["error"]["code"], "currency_mismatch")

    def test_unknown_recipient(self):
        res = self.send(to="1000000000")
        self.assertEqual(res.status_code, 404)

    def test_lookup_masks_name(self):
        res = self.client.get("/api/v1/accounts/lookup/", {"account_number": self.b_acc.account_number})
        self.assertEqual(res.data["holder_name"], "Bob M.")

    def test_transaction_list_is_scoped_and_filterable(self):
        self.send()
        res = self.client.get("/api/v1/transactions/", {"type": "DEBIT"})
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["category"], "TRANSFER_OUT")
        all_mine = self.client.get("/api/v1/transactions/").data
        self.assertEqual(all_mine["count"], 2)  # bonus + debit; Bob's credit is not visible
        other = Transaction.objects.filter(account=self.b_acc).first()
        self.assertEqual(self.client.get(f"/api/v1/transactions/{other.id}/").status_code, 404)

    def test_requires_auth(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/v1/accounts/").status_code, 401)
