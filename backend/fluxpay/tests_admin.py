"""Every back-office page renders, with data, for an admin; limited staff see only what they may use."""

from decimal import Decimal

from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from banking.services import open_wallet, post_adjustment, transfer_funds
from organizations import services as org_services
from organizations.models import Membership

User = get_user_model()
PASSWORD = "Str0ng-Pass!42"


class AdminPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("admin@example.com", PASSWORD, full_name="Ada Admin")
        alice = User.objects.create_user("alice@example.com", PASSWORD, full_name="Alice Kamau")
        bob = User.objects.create_user("bob@example.com", PASSWORD, full_name="Bob Mwangi")
        a, b = open_wallet(alice), open_wallet(bob)
        post_adjustment(
            staff=cls.admin,
            account_id=a.id,
            kind="CREDIT",
            amount=Decimal("900.00"),
            reason="Cash deposited at the Nairobi office, receipt 1042",
        )
        transfer_funds(
            user=alice,
            source_id=a.id,
            destination_number=b.account_number,
            amount=Decimal("100.00"),
            note="Lunch",
            idempotency_key="admin-pages-1",
        )
        org = org_services.create_organization(user=alice, name="Kamau Traders")
        membership = Membership.objects.get(organization=org, user=alice)
        org_services.invite_member(membership=membership, email="new@example.com", role="VIEWER")
        transfer_funds(
            user=alice,
            source_id=a.id,
            destination_number=org.accounts.get().account_number,
            amount=Decimal("300.00"),
            note="",
            idempotency_key="admin-pages-2",
        )
        org_services.create_payment_request(
            membership=membership,
            source_account_id=org.accounts.get().id,
            destination_account_number=b.account_number,
            amount=Decimal("200.00"),
            note="",
            idempotency_key="pr-1",
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_dashboard_shows_figures_and_actions(self):
        res = self.client.get(reverse("admin:index"))
        self.assertEqual(res.status_code, 200)
        for text in (
            "Top up a wallet",
            "Needs attention",
            "Customer money held",
            "Recent top-ups",
            "Intact",
            "Business payments waiting for approval",
        ):
            self.assertContains(res, text)
        self.assertContains(res, "Production")  # tests run with DEBUG off; the dev server shows "Development"

    def test_every_registered_screen_lists_and_opens(self):
        for model, model_admin in admin.site._registry.items():
            meta = model._meta
            with self.subTest(model=meta.label):
                changelist = reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist")
                res = self.client.get(changelist, follow=True)
                self.assertEqual(res.status_code, 200, changelist)
                first = model.objects.first()
                if first is not None:
                    page = reverse(f"admin:{meta.app_label}_{meta.model_name}_change", args=[first.pk])
                    self.assertEqual(self.client.get(page).status_code, 200, page)

    def test_list_filters_and_search_work(self):
        url = reverse("admin:banking_transaction_changelist")
        self.assertEqual(self.client.get(url, {"q": "Lunch"}).status_code, 200)
        self.assertEqual(self.client.get(url, {"type__exact": "CREDIT"}).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("admin:banking_account_changelist"), {"type": "business"}).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("admin:audit_auditevent_changelist"), {"area": "adjustment."}).status_code, 200
        )

    def test_top_up_form_renders(self):
        res = self.client.get(reverse("admin:banking_manualadjustment_add"))
        self.assertContains(res, "Find the wallet by account number")

    def test_staff_see_only_what_they_may_use(self):
        support = User.objects.create_user("support@example.com", PASSWORD, full_name="Sam Support", is_staff=True)
        support.user_permissions.add(Permission.objects.get(codename="post_adjustment"))
        self.client.force_login(support)
        res = self.client.get(reverse("admin:index"))
        self.assertContains(res, reverse("admin:banking_manualadjustment_changelist"))
        self.assertNotContains(res, reverse("admin:audit_auditevent_changelist"))  # no permission: not in the menu
        self.assertEqual(self.client.get(reverse("admin:audit_auditevent_changelist")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:banking_manualadjustment_add")).status_code, 200)

    def test_every_app_model_with_data_is_reachable_from_the_menu(self):
        res = self.client.get(reverse("admin:index"))
        for label in (
            "banking.Account",
            "banking.Transaction",
            "banking.ManualAdjustment",
            "organizations.Organization",
            "audit.AuditEvent",
            "platform_settings.Currency",
            "notifications.Notification",
        ):
            meta = apps.get_model(label)._meta
            self.assertContains(res, reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist"))
