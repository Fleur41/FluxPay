import re
import threading
from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from audit.models import AuditEvent
from banking.models import Transaction
from banking.services import open_wallet, transfer_funds
from fluxpay.celery import app as celery_app
from fluxpay.testing import funded
from fluxpay.exceptions import BusinessError
from payments import services as payment_services
from payments.models import ExternalPayment

from . import services
from .models import Invitation, Membership, Organization, PaymentRequest

User = get_user_model()
FAKE = {"FAKE": "payments.providers.fake.FakeProvider"}


def make_user(email, name):
    user = User.objects.create_user(email, "Str0ng-Pass!42", full_name=name)
    open_wallet(user, currency="KES")
    return user


def personal_wallet(user):
    return user.accounts.get(organization__isnull=True)


@funded
@override_settings(FLUXPAY_PAYMENT_PROVIDERS=FAKE)
class BusinessTestCase(APITestCase):
    def setUp(self):
        self.owner = make_user("olivia@acme.test", "Olivia Owner")
        self.org = services.create_organization(user=self.owner, name="Acme Ltd", registration_number="PVT-123")
        self.wallet = self.org.accounts.get()
        self.outsider = make_user("oscar@other.test", "Oscar Outsider")
        # Fund the business from the owner's personal wallet.
        transfer_funds(
            user=self.owner,
            source_id=personal_wallet(self.owner).id,
            destination_number=self.wallet.account_number,
            amount=Decimal("800.00"),
            note="Capital",
            idempotency_key="fund-business-1",
        )

    def add_member(self, email, name, role):
        user = make_user(email, name)
        Membership.objects.create(organization=self.org, user=user, role=role, invited_by=self.owner)
        return user

    def as_user(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def url(self, suffix=""):
        return f"/api/v1/organizations/{self.org.id}/{suffix}"

    def balance(self, account):
        account.refresh_from_db()
        return account.balance

    def pay(self, user, amount, key, to=None):
        return self.as_user(user).post(
            self.url("payment-requests/"),
            {
                "source_account_id": str(self.wallet.id),
                "destination_account_number": to or personal_wallet(self.outsider).account_number,
                "amount": amount,
                "note": "Supplier invoice",
                "idempotency_key": key,
            },
            format="json",
        )


class OrganizationTests(BusinessTestCase):
    def test_creating_a_business_makes_you_owner_with_an_empty_wallet(self):
        res = self.as_user(self.outsider).post("/api/v1/organizations/", {"name": "Oscar Shop"}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["my_role"], "OWNER")
        org = Organization.objects.get(id=res.data["id"])
        self.assertEqual(org.accounts.get().balance, Decimal("0.00"))  # no signup bonus for businesses
        self.assertTrue(AuditEvent.objects.filter(action="org.created", organization_id=org.id).exists())

        listing = self.as_user(self.outsider).get("/api/v1/organizations/")
        self.assertEqual([o["name"] for o in listing.data], ["Oscar Shop"])

    def test_non_members_cannot_see_the_business(self):
        for path in ("", "members/", "accounts/", "transactions/", "payment-requests/"):
            res = self.as_user(self.outsider).get(self.url(path))
            self.assertEqual(res.status_code, 404, path)
            self.assertEqual(res.data["error"]["code"], "organization_not_found")

    def test_members_see_business_wallet_and_its_transactions(self):
        viewer = self.add_member("vera@acme.test", "Vera Viewer", Membership.Role.VIEWER)
        accounts = self.as_user(viewer).get(self.url("accounts/"))
        self.assertEqual(accounts.data[0]["balance"], "800.00")
        txns = self.as_user(viewer).get(self.url("transactions/"))
        self.assertEqual(txns.data["results"][0]["description"], "Capital")

    def test_only_owners_change_settings(self):
        admin = self.add_member("adam@acme.test", "Adam Admin", Membership.Role.ADMIN)
        res = self.as_user(admin).patch(self.url(), {"approval_threshold": "500.00"}, format="json")
        self.assertEqual(res.status_code, 403)
        res = self.as_user(self.owner).patch(self.url(), {"approval_threshold": "500.00"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["approval_threshold"], "500.00")
        event = AuditEvent.objects.get(action="org.settings_changed")
        self.assertEqual(event.metadata, {"before": {"approval_threshold": "0.00"}, "after": {"approval_threshold": "500.00"}})

    def test_suspended_business_is_read_only(self):
        self.org.status = Organization.Status.SUSPENDED
        self.org.save()
        self.assertEqual(self.as_user(self.owner).get(self.url()).status_code, 200)
        res = self.pay(self.owner, "10.00", "suspended-1")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["error"]["code"], "organization_suspended")


class BusinessWalletIsolationTests(BusinessTestCase):
    """Business money must only move through approved payment requests."""

    def test_business_wallet_is_not_a_personal_account(self):
        res = self.as_user(self.owner).get("/api/v1/accounts/")
        self.assertEqual([a["id"] for a in res.data], [str(personal_wallet(self.owner).id)])
        res = self.as_user(self.owner).get("/api/v1/transactions/")
        self.assertNotIn(self.wallet.id, {t["account_id"] for t in res.data["results"]})

    def test_personal_transfer_endpoint_cannot_spend_business_money(self):
        res = self.as_user(self.owner).post(
            "/api/v1/transfers/",
            {
                "source_account_id": str(self.wallet.id),
                "destination_account_number": personal_wallet(self.outsider).account_number,
                "amount": "100.00",
                "idempotency_key": "sneaky-transfer-1",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self.balance(self.wallet), Decimal("800.00"))

    def test_personal_payout_cannot_spend_business_money(self):
        with self.assertRaises(BusinessError) as ctx:
            payment_services.start_payout(
                user=self.owner,
                account_id=self.wallet.id,
                rail="FAKE",
                method=ExternalPayment.Method.FAKE_OUT,
                amount=Decimal("100.00"),
                idempotency_key="sneaky-payout-1",
            )
        self.assertEqual(ctx.exception.error_code, "account_not_found")

    def test_lookup_and_receipts_show_the_business_name(self):
        res = self.as_user(self.outsider).get("/api/v1/accounts/lookup/", {"account_number": self.wallet.account_number})
        self.assertEqual(res.data["holder_name"], "Acme Ltd")


class InvitationTests(BusinessTestCase):
    def invite(self, by, email, role):
        with self.captureOnCommitCallbacks(execute=True):  # the email is sent once the invitation commits
            return self.as_user(by).post(self.url("invitations/"), {"email": email, "role": role}, format="json")

    def token_from_email(self):
        return re.search(r"token=([\w-]+)", mail.outbox[-1].body).group(1)

    def test_invite_and_accept(self):
        res = self.invite(self.owner, "Fiona@Acme.test", "FINANCE")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertNotIn("token", res.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Acme Ltd", mail.outbox[0].subject)
        token = self.token_from_email()
        self.assertNotIn(token, Invitation.objects.get().token_hash)  # only the hash is stored

        wrong = make_user("someone@else.test", "Some One")
        res = self.as_user(wrong).post("/api/v1/invitations/accept/", {"token": token}, format="json")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["error"]["code"], "invitation_email_mismatch")

        fiona = make_user("fiona@acme.test", "Fiona Finance")
        res = self.as_user(fiona).post("/api/v1/invitations/accept/", {"token": token}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["my_role"], "FINANCE")

        again = self.as_user(fiona).post("/api/v1/invitations/accept/", {"token": token}, format="json")
        self.assertEqual(again.data["error"]["code"], "invitation_invalid")
        self.assertTrue(AuditEvent.objects.filter(action="org.member.joined", actor=fiona).exists())

    def test_expired_and_revoked_invitations_do_not_work(self):
        self.invite(self.owner, "late@acme.test", "VIEWER")
        token = self.token_from_email()
        Invitation.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        late = make_user("late@acme.test", "Late Person")
        res = self.as_user(late).post("/api/v1/invitations/accept/", {"token": token}, format="json")
        self.assertEqual(res.data["error"]["code"], "invitation_invalid")

        self.invite(self.owner, "late@acme.test", "VIEWER")
        token = self.token_from_email()
        invitation = Invitation.objects.filter(revoked_at__isnull=True).get()
        self.assertEqual(self.as_user(self.owner).delete(self.url(f"invitations/{invitation.id}/")).status_code, 204)
        res = self.as_user(late).post("/api/v1/invitations/accept/", {"token": token}, format="json")
        self.assertEqual(res.data["error"]["code"], "invitation_invalid")

    def test_admins_invite_staff_but_not_admins_or_owners(self):
        admin = self.add_member("adam@acme.test", "Adam Admin", Membership.Role.ADMIN)
        self.assertEqual(self.invite(admin, "v@acme.test", "VIEWER").status_code, 201)
        self.assertEqual(self.invite(admin, "a@acme.test", "ADMIN").status_code, 403)
        self.assertEqual(self.invite(admin, "o@acme.test", "OWNER").status_code, 403)

    def test_finance_and_viewers_cannot_invite(self):
        finance = self.add_member("fiona@acme.test", "Fiona Finance", Membership.Role.FINANCE)
        self.assertEqual(self.invite(finance, "v@acme.test", "VIEWER").status_code, 403)

    def test_cannot_invite_an_existing_member(self):
        self.add_member("vera@acme.test", "Vera Viewer", Membership.Role.VIEWER)
        res = self.invite(self.owner, "vera@acme.test", "VIEWER")
        self.assertEqual(res.data["error"]["code"], "already_member")


class MembershipTests(BusinessTestCase):
    def member_id(self, user):
        return Membership.objects.get(organization=self.org, user=user).id

    def test_owner_changes_roles_and_it_is_audited(self):
        vera = self.add_member("vera@acme.test", "Vera Viewer", Membership.Role.VIEWER)
        res = self.as_user(self.owner).patch(self.url(f"members/{self.member_id(vera)}/"), {"role": "FINANCE"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        event = AuditEvent.objects.get(action="org.member.role_changed")
        self.assertEqual((event.metadata["from"], event.metadata["to"]), ("VIEWER", "FINANCE"))

    def test_admin_cannot_promote_to_admin_or_touch_owners(self):
        admin = self.add_member("adam@acme.test", "Adam Admin", Membership.Role.ADMIN)
        vera = self.add_member("vera@acme.test", "Vera Viewer", Membership.Role.VIEWER)
        client = self.as_user(admin)
        self.assertEqual(client.patch(self.url(f"members/{self.member_id(vera)}/"), {"role": "ADMIN"}, format="json").status_code, 403)
        self.assertEqual(client.delete(self.url(f"members/{self.member_id(self.owner)}/")).status_code, 403)
        self.assertEqual(client.patch(self.url(f"members/{self.member_id(vera)}/"), {"role": "FINANCE"}, format="json").status_code, 200)

    def test_the_last_owner_cannot_leave_or_be_demoted(self):
        res = self.as_user(self.owner).delete(self.url(f"members/{self.member_id(self.owner)}/"))
        self.assertEqual(res.data["error"]["code"], "last_owner")
        second = self.add_member("sam@acme.test", "Sam Second", Membership.Role.OWNER)
        res = self.as_user(second).patch(self.url(f"members/{self.member_id(self.owner)}/"), {"role": "ADMIN"}, format="json")
        self.assertEqual(res.status_code, 200)  # fine now: Sam is still an owner
        res = self.as_user(self.owner).patch(self.url(f"members/{self.member_id(second)}/"), {"role": "ADMIN"}, format="json")
        self.assertEqual(res.status_code, 403)  # Olivia is an admin now

    def test_cannot_change_own_role(self):
        res = self.as_user(self.owner).patch(self.url(f"members/{self.member_id(self.owner)}/"), {"role": "VIEWER"}, format="json")
        self.assertEqual(res.data["error"]["code"], "own_role")

    def test_anyone_can_leave(self):
        vera = self.add_member("vera@acme.test", "Vera Viewer", Membership.Role.VIEWER)
        self.assertEqual(self.as_user(vera).delete(self.url(f"members/{self.member_id(vera)}/")).status_code, 204)
        self.assertEqual(self.as_user(vera).get(self.url()).status_code, 404)

    def test_removed_member_loses_access(self):
        fiona = self.add_member("fiona@acme.test", "Fiona Finance", Membership.Role.FINANCE)
        self.as_user(self.owner).delete(self.url(f"members/{self.member_id(fiona)}/"))
        self.assertEqual(self.pay(fiona, "10.00", "after-removal").status_code, 404)


class PaymentApprovalTests(BusinessTestCase):
    def setUp(self):
        super().setUp()
        self.fiona = self.add_member("fiona@acme.test", "Fiona Finance", Membership.Role.FINANCE)
        self.adam = self.add_member("adam@acme.test", "Adam Admin", Membership.Role.ADMIN)
        self.recipient = personal_wallet(self.outsider)

    def decide(self, user, request_id, decision, note=""):
        return self.as_user(user).post(
            self.url(f"payment-requests/{request_id}/{decision}/"), {"note": note}, format="json"
        )

    def test_payment_up_to_threshold_is_sent_straight_away(self):
        self.org.approval_threshold = Decimal("200.00")
        self.org.save()
        res = self.pay(self.fiona, "150.00", "small-pay-1")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["status"], "EXECUTED")
        self.assertIsNotNone(res.data["reference"])
        self.assertEqual(self.balance(self.wallet), Decimal("650.00"))
        self.assertEqual(self.balance(self.recipient), Decimal("1150.00"))
        received = Transaction.objects.get(account=self.recipient, type="CREDIT", reference=res.data["reference"])
        self.assertEqual(received.counterparty_name, "Acme Ltd")

    def test_large_payment_waits_for_a_second_person(self):
        res = self.pay(self.fiona, "300.00", "big-pay-1")
        self.assertEqual(res.data["status"], "PENDING_APPROVAL")
        self.assertEqual(self.balance(self.wallet), Decimal("800.00"))
        request_id = res.data["id"]

        self.assertEqual(self.decide(self.fiona, request_id, "approve").status_code, 403)  # finance can't approve

        res = self.decide(self.adam, request_id, "approve", "Invoice checked")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], "EXECUTED")
        self.assertEqual(res.data["decided_by"], "adam@acme.test")
        self.assertEqual(self.balance(self.wallet), Decimal("500.00"))
        self.assertEqual(self.balance(self.recipient), Decimal("1300.00"))

        again = self.decide(self.owner, request_id, "approve")
        self.assertEqual(again.data["error"]["code"], "not_pending")
        self.assertEqual(self.balance(self.wallet), Decimal("500.00"))
        actions = list(AuditEvent.objects.filter(organization_id=self.org.id, action__startswith="org.payment").order_by("id").values_list("action", flat=True))
        self.assertEqual(actions, ["org.payment.created", "org.payment.approved", "org.payment.executed"])

    def test_nobody_approves_their_own_payment(self):
        res = self.pay(self.adam, "300.00", "own-pay-1")
        res = self.decide(self.adam, res.data["id"], "approve")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["error"]["code"], "self_approval")

    def test_rejected_payment_moves_no_money(self):
        res = self.pay(self.fiona, "300.00", "reject-pay-1")
        res = self.decide(self.adam, res.data["id"], "reject", "Wrong supplier")
        self.assertEqual(res.data["status"], "REJECTED")
        self.assertEqual(res.data["decision_note"], "Wrong supplier")
        self.assertEqual(self.balance(self.wallet), Decimal("800.00"))

    def test_only_the_creator_cancels(self):
        res = self.pay(self.fiona, "300.00", "cancel-pay-1")
        request_id = res.data["id"]
        self.assertEqual(self.decide(self.adam, request_id, "cancel").status_code, 403)
        self.assertEqual(self.decide(self.fiona, request_id, "cancel").data["status"], "CANCELLED")

    def test_approval_without_funds_fails_cleanly(self):
        res = self.pay(self.fiona, "900.00", "too-big-1")
        res = self.decide(self.adam, res.data["id"], "approve")
        self.assertEqual(res.data["status"], "FAILED")
        self.assertEqual(res.data["failure_reason"], "Insufficient funds for this transfer.")
        self.assertEqual(self.balance(self.wallet), Decimal("800.00"))
        self.assertTrue(AuditEvent.objects.filter(action="org.payment.failed").exists())

    def test_retry_with_same_key_is_one_payment(self):
        first = self.pay(self.fiona, "300.00", "same-key-01")
        second = self.pay(self.fiona, "300.00", "same-key-01")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(PaymentRequest.objects.count(), 1)

    def test_viewers_cannot_initiate(self):
        vera = self.add_member("vera@acme.test", "Vera Viewer", Membership.Role.VIEWER)
        self.assertEqual(self.pay(vera, "10.00", "viewer-pay-1").status_code, 403)

    def test_unknown_decision_is_not_found(self):
        res = self.pay(self.fiona, "300.00", "unknown-dec-1")
        self.assertEqual(self.decide(self.adam, res.data["id"], "frobnicate").status_code, 404)

    def test_pending_list_filter(self):
        self.pay(self.fiona, "300.00", "list-pay-1")
        res = self.as_user(self.adam).get(self.url("payment-requests/"), {"status": "PENDING_APPROVAL"})
        self.assertEqual(res.data["count"], 1)


class OrgAuditApiTests(BusinessTestCase):
    def test_owners_and_admins_read_only_their_business_audit_log(self):
        finance = self.add_member("fiona@acme.test", "Fiona Finance", Membership.Role.FINANCE)
        self.assertEqual(self.as_user(finance).get(self.url("audit-events/")).status_code, 403)
        services.create_organization(user=self.outsider, name="Other Co")  # another business's events
        self.pay(finance, "300.00", "audit-pay-1")

        res = self.as_user(self.owner).get(self.url("audit-events/"))
        self.assertEqual(res.status_code, 200)
        actions = [e["action"] for e in res.data["results"]]
        self.assertEqual(actions, ["org.payment.created", "org.created"])  # newest first; nothing from Other Co
        self.assertEqual(res.data["results"][0]["actor_label"], "fiona@acme.test")

        filtered = self.as_user(self.owner).get(self.url("audit-events/"), {"action": "org.payment"})
        self.assertEqual([e["action"] for e in filtered.data["results"]], ["org.payment.created"])


@skipUnless(connection.vendor == "postgresql", "needs real row locks (PostgreSQL)")
@funded
class ApprovalRaceTests(TransactionTestCase):
    serialized_rollback = True  # keep the platform settings rows the data migration created

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Commits are real here, so after-commit jobs (alerts) run: keep them inline, whatever the broker.
        conf = celery_app.conf
        cls._eager = (conf.task_always_eager, conf.task_eager_propagates)
        conf.update(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)

    @classmethod
    def tearDownClass(cls):
        eager, propagates = cls._eager
        celery_app.conf.update(CELERY_TASK_ALWAYS_EAGER=eager, CELERY_TASK_EAGER_PROPAGATES=propagates)
        super().tearDownClass()

    def test_two_approvers_at_once_pay_once(self):
        owner = make_user("olivia@acme.test", "Olivia Owner")
        org = services.create_organization(user=owner, name="Acme Ltd")
        wallet = org.accounts.get()
        transfer_funds(user=owner, source_id=personal_wallet(owner).id, destination_number=wallet.account_number,
                       amount=Decimal("800.00"), note="", idempotency_key="fund-race-1")
        approvers = []
        for i in range(3):
            user = make_user(f"admin{i}@acme.test", f"Admin {i}")
            approvers.append(Membership.objects.create(organization=org, user=user, role=Membership.Role.ADMIN))
        recipient = make_user("oscar@other.test", "Oscar Outsider")
        creator = Membership.objects.get(organization=org, user=owner)
        request, _ = services.create_payment_request(
            membership=creator, source_account_id=wallet.id,
            destination_account_number=personal_wallet(recipient).account_number,
            amount=Decimal("300.00"), note="", idempotency_key="race-pay-1",
        )
        barrier, outcomes = threading.Barrier(3), []

        def approve(membership):
            try:
                barrier.wait()
                membership = Membership.objects.select_related("organization", "user").get(id=membership.id)
                services.approve_payment_request(membership=membership, request_id=request.id)
                outcomes.append("approved")
            except BusinessError as exc:
                outcomes.append(exc.error_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=approve, args=(m,)) for m in approvers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sorted(outcomes), ["approved", "not_pending", "not_pending"])
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("500.00"))
