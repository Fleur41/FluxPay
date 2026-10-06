"""Two-step verification: the TOTP maths, signing in with it, and who must use it."""

import base64
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from audit.models import AuditEvent
from banking.services import open_wallet, transfer_funds
from organizations import services as orgs
from organizations.models import Membership

from . import mfa
from .models import MfaRecoveryCode, User

PASSWORD = "Str0ng-Pass!42"


class TotpTests(TestCase):
    def test_rfc_6238_test_vectors(self):
        # RFC 6238 appendix B, SHA-1, 8-digit codes; ours are the last 6 digits of the same number.
        secret = base64.b32encode(b"12345678901234567890").decode()
        for t, expected in ((59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
                            (1234567890, "89005924"), (2000000000, "69279037"), (20000000000, "65353130")):  # fmt: skip
            self.assertEqual(mfa.code_at(secret, mfa.current_counter(t)), expected[-6:], t)

    def test_secret_is_stored_encrypted(self):
        user = User.objects.create_user("e@x.test", PASSWORD, full_name="E")
        secret, uri = mfa.begin_setup(user)
        user.refresh_from_db()
        self.assertNotIn(secret, user.mfa_pending_secret)
        self.assertEqual(mfa.decrypt(user.mfa_pending_secret), secret)
        self.assertIn(f"secret={secret}", uri)


class MfaApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("amina@x.test", PASSWORD, full_name="Amina")

    def code(self, secret, offset=0):
        return mfa.code_at(secret, mfa.current_counter() + offset)

    def turn_on(self):
        self.client.force_authenticate(self.user)
        secret = self.client.post("/api/v1/auth/mfa/setup/").data["secret"]
        res = self.client.post("/api/v1/auth/mfa/enable/", {"code": self.code(secret)})
        self.assertEqual(res.status_code, 200, res.data)
        self.client.force_authenticate(None)
        return secret, res.data["recovery_codes"]

    def login(self):
        return self.client.post("/api/v1/auth/login/", {"email": "Amina@x.test", "password": PASSWORD}).data

    def test_sign_in_needs_a_code_once_turned_on(self):
        self.assertIn("access", self.login())  # off: tokens straight away
        secret, recovery = self.turn_on()
        self.assertEqual(len(recovery), 10)

        first = self.login()
        self.assertEqual((first["mfa_required"], "access" in first), (True, False))
        wrong = self.client.post("/api/v1/auth/login/mfa/", {"mfa_token": first["mfa_token"], "code": "000000"})
        self.assertEqual(wrong.data["error"]["code"], "mfa_invalid_code")
        res = self.client.post("/api/v1/auth/login/mfa/", {"mfa_token": first["mfa_token"], "code": self.code(secret, 1)})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIn("access", res.data)
        self.assertTrue(res.data["user"]["mfa_enabled"])

        # The same code can't be used twice (someone looking over a shoulder), nor an older one.
        again = self.client.post("/api/v1/auth/login/mfa/", {"mfa_token": self.login()["mfa_token"],
                                                             "code": self.code(secret, 1)})  # fmt: skip
        self.assertEqual(again.data["error"]["code"], "mfa_invalid_code")

    def test_recovery_codes_work_once(self):
        _secret, recovery = self.turn_on()
        token = self.login()["mfa_token"]
        self.assertEqual(self.client.post("/api/v1/auth/login/mfa/", {"mfa_token": token, "code": recovery[0].lower()}).status_code, 200)
        reused = self.client.post("/api/v1/auth/login/mfa/", {"mfa_token": self.login()["mfa_token"], "code": recovery[0]})
        self.assertEqual(reused.status_code, 400)
        self.assertEqual(MfaRecoveryCode.objects.filter(user=self.user, used_at__isnull=True).count(), 9)

    def test_five_wrong_codes_lock_it_for_a_while(self):
        secret, _ = self.turn_on()
        for _ in range(5):
            self.client.post("/api/v1/auth/login/mfa/", {"mfa_token": self.login()["mfa_token"], "code": "123456"})
        res = self.client.post("/api/v1/auth/login/mfa/", {"mfa_token": self.login()["mfa_token"], "code": self.code(secret)})
        self.assertEqual((res.status_code, res.data["error"]["code"]), (429, "mfa_locked"))
        self.assertTrue(AuditEvent.objects.filter(action="auth.mfa_locked").exists())

    def test_challenge_expires_when_the_password_changes(self):
        secret, _ = self.turn_on()
        token = self.login()["mfa_token"]
        self.user.set_password("An0ther-Pass!42")
        self.user.save()
        res = self.client.post("/api/v1/auth/login/mfa/", {"mfa_token": token, "code": self.code(secret)})
        self.assertEqual(res.data["error"]["code"], "mfa_challenge_expired")

    def test_turning_it_off_needs_password_and_code(self):
        secret, _ = self.turn_on()
        self.client.force_authenticate(self.user)
        res = self.client.post("/api/v1/auth/mfa/disable/", {"password": "wrong", "code": self.code(secret)})
        self.assertEqual(res.status_code, 403)
        res = self.client.post("/api/v1/auth/mfa/disable/", {"password": PASSWORD, "code": self.code(secret, 1)})
        self.assertEqual(res.status_code, 204)
        self.assertFalse(self.client.get("/api/v1/auth/mfa/").data["enabled"])


@override_settings(FLUXPAY_REQUIRE_BUSINESS_MFA=True)
class BusinessMfaTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("owner@x.test", PASSWORD, full_name="Owner")
        wallet = open_wallet(self.owner)
        wallet.balance = Decimal("1000")
        wallet.save()
        self.org = orgs.create_organization(user=self.owner, name="Acme")
        transfer_funds(user=self.owner, source_id=wallet.id, destination_number=self.org.accounts.get().account_number,
                       amount=Decimal("500"), note="", idempotency_key="capital-1")  # fmt: skip
        self.finance = User.objects.create_user("fin@x.test", PASSWORD, full_name="Fin")
        Membership.objects.create(organization=self.org, user=self.finance, role=Membership.Role.FINANCE)
        self.payee = open_wallet(User.objects.create_user("payee@x.test", PASSWORD, full_name="Payee"))

    def pay(self, user, key):
        self.client.force_authenticate(user)
        return self.client.post(f"/api/v1/organizations/{self.org.id}/payments/", {
            "type": "SUPPLIER", "destination_account_number": self.payee.account_number, "amount": "10",
            "idempotency_key": key,
        })  # fmt: skip

    def test_owners_need_it_to_act_but_can_still_look(self):
        res = self.pay(self.owner, "owner-pay-1")
        self.assertEqual((res.status_code, res.data["error"]["code"]), (403, "mfa_required"))
        self.assertEqual(self.client.get(f"/api/v1/organizations/{self.org.id}/payments/").status_code, 200)
        # Looking includes the audit log: that's where owners see FluxPay staff looking at their business.
        self.assertEqual(self.client.get(f"/api/v1/organizations/{self.org.id}/audit-events/").status_code, 200)
        self.assertTrue(self.client.get("/api/v1/auth/me/").data["mfa_required"])

        self.assertEqual(self.pay(self.finance, "finance-pay-1").status_code, 201)  # finance: not required

        secret, _ = mfa.begin_setup(self.owner)
        mfa.enable(self.owner, mfa.code_at(secret, mfa.current_counter()))
        self.owner.refresh_from_db()
        self.assertEqual(self.pay(self.owner, "owner-pay-2").status_code, 201)


@override_settings(FLUXPAY_REQUIRE_STAFF_MFA=True)
class StaffMfaTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = User.objects.create_superuser("ops@fluxpay.test", PASSWORD, full_name="Ops")

    def test_back_office_needs_the_second_step_each_session(self):
        self.client.force_login(self.staff)
        res = self.client.get("/admin/")
        self.assertRedirects(res, "/admin/mfa/?next=/admin/", fetch_redirect_response=False)
        page = self.client.get("/admin/mfa/")
        self.assertContains(page, "Enter a setup key")
        secret = mfa.decrypt(User.objects.get(pk=self.staff.pk).mfa_pending_secret)

        wrong = self.client.post("/admin/mfa/", {"code": "000000", "next": "/admin/"})
        self.assertContains(wrong, "That code isn&#x27;t right")
        done = self.client.post("/admin/mfa/", {"code": mfa.code_at(secret, mfa.current_counter()), "next": "/admin/"})
        self.assertContains(done, "recovery codes")
        self.assertEqual(self.client.get("/admin/").status_code, 200)

        self.client.logout()
        self.client.force_login(self.staff)  # a new session: the code again
        self.assertEqual(self.client.get("/admin/organizations/payment/").status_code, 302)
        with mock.patch("users.mfa.current_counter", return_value=mfa.current_counter() + 1):
            self.client.post("/admin/mfa/", {"code": mfa.code_at(secret, mfa.current_counter() + 1), "next": "/admin/"})
        self.assertEqual(self.client.get("/admin/organizations/payment/").status_code, 200)
