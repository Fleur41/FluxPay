from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from fluxpay.testing import funded

from banking.services import open_wallet, transfer_funds

from .models import AuditChainHead, AuditEvent
from .services import record, verify_chain

User = get_user_model()
PASSWORD = "Str0ng-Pass!42"


class HashChainTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("auditor@example.com", PASSWORD, full_name="Ada Auditor")
        self.events = [record("test.event", actor=self.user, metadata={"n": i}) for i in range(5)]

    def test_intact_chain_verifies(self):
        self.assertIsNone(verify_chain())
        out = StringIO()
        call_command("verify_audit_log", stdout=out)
        self.assertIn("intact (5 events)", out.getvalue())

    def test_each_event_links_to_the_previous_one(self):
        events = list(AuditEvent.objects.order_by("id"))
        self.assertEqual(events[0].prev_hash, "0" * 64)
        for before, after in zip(events, events[1:]):
            self.assertEqual(after.prev_hash, before.hash)

    def test_editing_an_event_is_detected(self):
        target = self.events[2]
        AuditEvent.objects.filter(id=target.id).update(metadata={"n": 999})  # bypasses the app, like a DB edit
        self.assertEqual(verify_chain(), target.id)
        with self.assertRaisesMessage(CommandError, f"broken at event #{target.id}"):
            call_command("verify_audit_log")

    def test_deleting_from_the_middle_is_detected(self):
        AuditEvent.objects.filter(id=self.events[1].id).delete()
        self.assertEqual(verify_chain(), self.events[2].id)

    def test_deleting_from_the_end_is_detected(self):
        AuditEvent.objects.filter(id=self.events[-1].id).delete()
        self.assertEqual(verify_chain(), -1)

    def test_rewriting_an_event_and_its_hash_breaks_the_next_link(self):
        target = self.events[1]
        target.metadata = {"n": 999}
        from .services import compute_hash

        AuditEvent.objects.filter(id=target.id).update(metadata=target.metadata, hash=compute_hash(target))
        self.assertEqual(verify_chain(), self.events[2].id)

    def test_head_tracks_the_latest_hash(self):
        self.assertEqual(AuditChainHead.objects.get().last_hash, self.events[-1].hash)


@funded
class AuditedActionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("amina@example.com", PASSWORD, full_name="Amina Wanjiru")
        self.wallet = open_wallet(self.user)

    def test_successful_login_is_recorded_with_ip_and_user_agent(self):
        res = self.client.post(
            "/api/v1/auth/login/",
            {"email": "amina@example.com", "password": PASSWORD},
            format="json",
            HTTP_USER_AGENT="FluxPay-Android/1.0",
            REMOTE_ADDR="10.1.2.3",
        )
        self.assertEqual(res.status_code, 200)
        event = AuditEvent.objects.get(action="auth.login")
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.ip_address, "10.1.2.3")
        self.assertEqual(event.user_agent, "FluxPay-Android/1.0")

    def test_registration_is_recorded(self):
        res = self.client.post(
            "/api/v1/auth/register/",
            {"email": "New@Example.com", "full_name": "New Person", "password": PASSWORD},
            format="json",
            REMOTE_ADDR="10.9.8.7",
        )
        self.assertEqual(res.status_code, 201, res.data)
        event = AuditEvent.objects.get(action="auth.registered")
        self.assertEqual(event.actor_label, "new@example.com")
        self.assertEqual(event.ip_address, "10.9.8.7")

    def test_failed_login_is_recorded_without_the_password(self):
        self.client.post("/api/v1/auth/login/", {"email": "Amina@Example.com", "password": "wrong-guess"}, format="json")
        event = AuditEvent.objects.get(action="auth.login_failed")
        self.assertIsNone(event.actor)
        self.assertEqual(event.metadata, {"email": "amina@example.com"})
        self.assertNotIn("wrong-guess", str(event.metadata) + event.user_agent)

    def test_transfers_are_recorded(self):
        other = User.objects.create_user("brian@example.com", PASSWORD, full_name="Brian Otieno")
        other_wallet = open_wallet(other)
        transfer, _, _ = transfer_funds(
            user=self.user,
            source_id=self.wallet.id,
            destination_number=other_wallet.account_number,
            amount=Decimal("25.00"),
            note="",
            idempotency_key="audit-transfer-1",
        )
        event = AuditEvent.objects.get(action="transfer.created")
        self.assertEqual(event.target_id, str(transfer.id))
        self.assertEqual(event.metadata["amount"], "25.00")
        self.assertEqual(event.metadata["to"], other_wallet.account_number)
        self.assertIsNone(verify_chain())

    def test_audit_log_cannot_be_edited_in_admin(self):
        from django.contrib import admin

        model_admin = admin.site._registry[AuditEvent]
        self.assertFalse(model_admin.has_change_permission(None))
        self.assertFalse(model_admin.has_delete_permission(None))
        self.assertFalse(model_admin.has_add_permission(None))
