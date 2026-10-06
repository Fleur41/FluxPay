"""The web pages that email links open: reset a password in the browser, and invitation codes."""

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from audit.models import AuditEvent

User = get_user_model()


@override_settings(FLUXPAY_WEB_URL="http://localhost:8000")
class WebLinkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("jane@example.com", "Old-Pass#123", full_name="Jane Doe")

    def reset_url(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        return f"/reset-password?uid={uid}&token={default_token_generator.make_token(self.user)}"

    def test_reset_email_link_opens_a_page_that_changes_the_password(self):
        self.client.post("/api/v1/auth/password-reset/", {"email": "jane@example.com"})
        link = next(line for line in mail.outbox[0].body.splitlines() if "/reset-password?" in line)
        self.assertTrue(link.startswith("http://localhost:8000/reset-password?uid="))
        path = link.removeprefix("http://localhost:8000")
        page = self.client.get(path)
        self.assertContains(page, "Choose a new password")
        self.assertContains(page, "jane@example.com")
        mismatch = self.client.post(path, {"password": "Brand-New-Pass#9", "password_again": "Other-Pass#9"})
        self.assertContains(mismatch, "don&#x27;t match")
        done = self.client.post(path, {"password": "Brand-New-Pass#9", "password_again": "Brand-New-Pass#9"})
        self.assertContains(done, "Password changed")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Brand-New-Pass#9"))
        self.assertEqual(AuditEvent.objects.get(action="auth.password_reset").metadata["via"], "web")
        self.assertContains(self.client.get(path), "This link has expired", status_code=400)  # works once

    def test_weak_password_is_refused_and_bad_links_say_so(self):
        res = self.client.post(self.reset_url(), {"password": "123", "password_again": "123"})
        self.assertContains(res, "too short")
        self.assertContains(self.client.get("/reset-password?uid=x&token=y"), "This link has expired", status_code=400)

    def test_invitation_pages_show_the_code_and_open_the_app(self):
        page = self.client.get("/join?code=AB12C3DE45")
        self.assertContains(page, "AB12C-3DE45")
        self.assertContains(page, "fluxpay://join-employer?code=AB12C3DE45")
        team = self.client.get("/join-business?token=tok_123")
        self.assertContains(team, "fluxpay://join-business?token=tok_123")
        self.assertContains(team, "Settings → Join a business team")
