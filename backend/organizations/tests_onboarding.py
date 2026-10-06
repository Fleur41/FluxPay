"""FluxPay staff onboard businesses from the back office, and see every business at a glance."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import TestCase

from audit.models import AuditEvent
from banking.models import Account

from .models import Membership, Organization

User = get_user_model()


class OnboardingTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("ops@fluxpay.dev", "Str0ng-Pass!42", full_name="Ops Person", is_staff=True)
        for codename in ("add_organization", "view_organization", "view_auditevent"):
            self.staff.user_permissions.add(Permission.objects.get(codename=codename))
        self.client.force_login(self.staff)

    def onboard(self, **fields):
        data = {"name": "Baraka Bakery", "registration_number": "PVT-123", "owner_name": "Baraka Otieno",
                "owner_email": "baraka@example.com", "owner_phone": "0712345678", **fields}  # fmt: skip
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post("/admin/organizations/organization/onboard/", data)

    def test_new_owner_gets_an_account_a_business_and_an_email_to_set_a_password(self):
        res = self.onboard()
        organization = Organization.objects.get(name="Baraka Bakery")
        self.assertRedirects(res, f"/admin/organizations/organization/{organization.pk}/change/",
                             fetch_redirect_response=False)  # fmt: skip
        owner = User.objects.get(email="baraka@example.com")
        self.assertFalse(owner.has_usable_password())
        self.assertEqual(Membership.objects.get(organization=organization).user, owner)
        self.assertTrue(Account.objects.filter(organization=organization).exists())  # the business wallet
        self.assertTrue(Account.objects.filter(owner=owner, organization__isnull=True).exists())  # their own
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("http://localhost:8000/reset-password?uid=", mail.outbox[0].body)
        event = AuditEvent.objects.get(action="org.onboarded")
        self.assertEqual((event.actor, event.metadata["new_owner"]), (self.staff, True))

    def test_existing_customer_just_gets_the_business(self):
        existing = User.objects.create_user("baraka@example.com", "Their-Own-Pass1", full_name="Baraka O.")
        with self.captureOnCommitCallbacks(execute=True):
            self.onboard(owner_email="Baraka@Example.com")
        existing.refresh_from_db()
        self.assertTrue(existing.check_password("Their-Own-Pass1"))  # untouched
        self.assertTrue(Membership.objects.filter(user=existing, role="OWNER").exists())
        self.assertNotIn("reset-password", mail.outbox[0].body)
        self.assertIn("Forgot password?", mail.outbox[0].body)

    def test_an_owner_who_never_set_a_password_gets_the_link_again(self):
        self.onboard()
        with self.captureOnCommitCallbacks(execute=True):
            self.onboard(name="Baraka Hardware")  # same owner, still no password
        self.assertIn("/reset-password?uid=", mail.outbox[-1].body)

    def test_staff_cant_own_a_business_and_names_are_unique(self):
        res = self.onboard(owner_email="ops@fluxpay.dev")
        self.assertContains(res, "staff accounts can&#x27;t own a business")
        self.onboard()
        res = self.onboard(owner_email="someone@example.com", name="baraka bakery")
        self.assertContains(res, "There is already a business called")

    def test_staff_without_permission_cant_onboard(self):
        self.staff.user_permissions.remove(Permission.objects.get(codename="add_organization"))
        self.assertEqual(self.onboard().status_code, 403)

    def test_dashboard_shows_every_business_and_live_activity(self):
        self.onboard()
        page = self.client.get("/admin/")
        self.assertContains(page, "Onboard a business")
        self.assertContains(page, "Baraka Bakery")
        self.assertContains(page, "Onboarded by FluxPay")
        logs = self.client.get("/admin/audit/auditevent/", {"organization": Organization.objects.get().pk})
        self.assertContains(logs, "org.onboarded")
