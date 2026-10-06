"""Becoming a worker: invitations, join codes with approval, suspension, leaving. Nobody joins without both sides."""

import re
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.utils import timezone

from organizations.models import Membership, Payment

from . import workers as register
from .models import Worker
from .tests import PASSWORD, PayrollTestCase, User

D = Decimal


class WorkerLifecycleTests(PayrollTestCase):

    def invite(self, sms, **body):
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(self.url("workers/"), {"salary": "10000", **body})
        self.assertEqual(res.status_code, 201, res.data)
        text = sms.return_value.send.call_args.args[1]
        return res.data, re.search(r"code ([0-9A-Z]{5}-[0-9A-Z]{5})", text).group(1)

    def as_worker(self, i):
        self.client.force_authenticate(self.workers[i].owner)

    @mock.patch("payroll.workers.get_sms_backend")
    def test_invited_by_phone_then_accepted_in_the_app(self, sms):
        worker, code = self.invite(sms, full_name="Wanjiru Kamau", phone_number="0711 000 003", email="w@x.test")
        self.assertEqual((worker["status"], worker["account_number"]), ("INVITED", ""))
        self.assertNotIn("code", worker)  # the business never sees the code
        self.assertEqual(sms.return_value.send.call_args.args[0], "+254711000003")
        self.assertIn(code, mail.outbox[0].body)
        self.assertIn("never sees your password", mail.outbox[0].body)

        self.as_worker(3)
        preview = self.client.post("/api/v1/worker-invitations/preview/", {"code": code.lower().replace("-", " ")})
        self.assertEqual((preview.data["business"], preview.data["name"]), ("Kamau Traders", "Wanjiru Kamau"))
        res = self.client.post("/api/v1/worker-invitations/accept/", {"code": code})
        self.assertEqual((res.data["status"], res.data["account_number"]), ("ACTIVE", self.workers[3].account_number))
        again = self.client.post("/api/v1/worker-invitations/accept/", {"code": code})
        self.assertEqual(again.data["error"]["code"], "invitation_invalid")  # used up
        self.assertEqual(Worker.objects.get(id=worker["id"]).name, "Worker 3")  # their own name from now on

    @mock.patch("payroll.workers.get_sms_backend")
    def test_invited_by_email_only_then_accepted(self, sms):
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(self.url("workers/"), {"salary": "10000", "full_name": "Achieng Otieno",
                                                          "email": "Achieng@Example.org"})  # fmt: skip
        self.assertEqual(res.status_code, 201, res.data)
        sms.return_value.send.assert_not_called()
        body = mail.outbox[0].body
        self.assertEqual(mail.outbox[0].to, ["achieng@example.org"])
        self.assertIn("Join a business", body)
        code = re.search(r"Your invitation code: ([0-9A-Z]{5}-[0-9A-Z]{5})", body).group(1)
        self.as_worker(3)
        accepted = self.client.post("/api/v1/worker-invitations/accept/", {"code": code})
        self.assertEqual(accepted.data["status"], "ACTIVE")

    def test_email_invitation_needs_a_name_and_isnt_sent_twice(self):
        res = self.client.post(self.url("workers/"), {"salary": "10000", "email": "a@example.org"})
        self.assertEqual(res.status_code, 400)
        self.client.post(self.url("workers/"), {"salary": "10000", "full_name": "A", "email": "a@example.org"})
        again = self.client.post(self.url("workers/"), {"salary": "10000", "full_name": "A", "email": "A@example.org"})
        self.assertEqual(again.data["error"]["code"], "already_invited")

    @mock.patch("payroll.workers.get_sms_backend")
    def test_email_still_goes_out_when_the_sms_provider_fails(self, sms):
        from notifications.sms import SmsError

        sms.return_value.send.side_effect = SmsError("401 Unauthorized")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url("workers/"), {"salary": "10000", "full_name": "Baraka",
                                                    "phone_number": "0711000004", "email": "b@example.org"})  # fmt: skip
        self.assertEqual(mail.outbox[0].to, ["b@example.org"])

    @mock.patch("payroll.workers.get_sms_backend")
    def test_an_invitation_to_an_account_is_for_that_person_only_and_expires(self, sms):
        _worker, code = self.invite(sms, account_number=self.workers[0].account_number)
        self.as_worker(1)
        res = self.client.post("/api/v1/worker-invitations/accept/", {"code": code})
        self.assertEqual(res.data["error"]["code"], "invitation_user_mismatch")

        self.client.force_authenticate(self.owner)
        _worker, code = self.invite(sms, full_name="Late", phone_number="0722000000")
        Worker.objects.filter(phone_number="+254722000000").update(invite_expires_at=timezone.now() - timedelta(1))
        self.as_worker(2)
        self.assertEqual(self.client.post("/api/v1/worker-invitations/accept/", {"code": code}).status_code, 404)

    def test_join_code_needs_approval_by_an_owner_or_admin(self):
        res = self.client.get(self.url("worker-join-code/"))
        self.assertEqual(res.data, {"enabled": False, "code": None, "link": None})
        code = self.client.post(self.url("worker-join-code/")).data["code"]

        self.as_worker(0)
        typed = code.replace("0", "o").lower()  # read off a poster: case and O/0 don't matter
        with self.captureOnCommitCallbacks(execute=True):  # emails the owners and admins
            res = self.client.post("/api/v1/employers/join/", {"code": typed})
        self.assertEqual((res.status_code, res.data["status"], res.data["business"]),
                         (201, "PENDING_ACTIVATION", "Kamau Traders"))  # fmt: skip
        self.assertEqual(self.client.post("/api/v1/employers/join/", {"code": code}).data["error"]["code"],
                         "already_worker")  # fmt: skip
        self.assertEqual(self.client.post("/api/v1/employers/join/", {"code": "ZZZZZ-ZZZZZ"}).status_code, 404)
        self.assertIn("asked to join Kamau Traders", mail.outbox[-1].subject)
        self.assertEqual(self.client.get(self.url("workers/")).status_code, 404)  # a worker isn't a member

        worker_id = Worker.objects.get(user=self.workers[0].owner).id
        self.client.force_authenticate(self.finance)
        self.assertEqual(self.client.post(self.url(f"workers/{worker_id}/approve/"), {"salary": "9000"}).status_code, 403)
        self.client.force_authenticate(self.owner)
        res = self.client.post(self.url(f"workers/{worker_id}/approve/"), {"salary": "9000", "job_title": "Cashier"})
        self.assertEqual((res.data["status"], res.data["salary"], res.data["account_number"]),
                         ("ACTIVE", "9000.00", self.workers[0].account_number))  # fmt: skip

        self.client.post(self.url("worker-join-code/"))  # a new code: the old one stops working
        self.as_worker(1)
        self.assertEqual(self.client.post("/api/v1/employers/join/", {"code": code}).status_code, 404)

    def test_declined_request_and_disabled_code(self):
        code = self.client.post(self.url("worker-join-code/")).data["code"]
        self.as_worker(0)
        request = self.client.post("/api/v1/employers/join/", {"code": code}).data
        self.client.force_authenticate(self.owner)
        res = self.client.post(self.url(f"workers/{request['id']}/decline/"), {"reason": "We don't know this person"})
        self.assertEqual(res.data["status"], "DEACTIVATED")
        self.client.delete(self.url("worker-join-code/"))
        self.as_worker(1)
        self.assertEqual(self.client.post("/api/v1/employers/join/", {"code": code}).status_code, 404)

    def test_suspended_workers_cant_be_paid(self):
        self.org.approval_threshold = D("1000000")
        self.org.save()
        self.add_workers("10000")
        run = self.create_run()  # all five, before the suspension
        worker = Worker.objects.get(wallet=self.workers[0])
        res = self.client.post(self.url(f"workers/{worker.id}/suspend/"), {"reason": "Under investigation"})
        self.assertEqual(res.data["status"], "SUSPENDED")

        res = self.client.post(self.url(f"pay-runs/{run['id']}/submit/"))
        self.assertEqual(res.data["error"]["code"], "worker_not_active")
        self.assertEqual(self.balance(self.business), D("50000"))  # nobody paid: all or nothing
        self.assertEqual(self.create_run("November")["worker_count"], 4)  # left out of new runs
        bonus = self.client.post(self.url("payments/"), {"type": "BONUS", "worker_id": str(worker.id), "amount": "100",
                                                         "idempotency_key": "bonus-suspended"})  # fmt: skip
        self.assertEqual(bonus.status_code, 404)

        self.assertEqual(self.client.post(self.url(f"workers/{worker.id}/reactivate/")).data["status"], "ACTIVE")
        self.client.post(self.url(f"pay-runs/{run['id']}/submit/"))
        self.assertEqual(self.balance(self.workers[0]), D("11000"))

    def test_leaving_keeps_the_pay_history_and_the_account(self):
        self.org.approval_threshold = D("1000000")
        self.org.save()
        self.add_workers("10000")
        run = self.create_run()
        self.client.post(self.url(f"pay-runs/{run['id']}/submit/"))

        self.as_worker(0)
        employers = self.client.get("/api/v1/employers/").data
        self.assertEqual([(e["business"], e["status"]) for e in employers], [("Kamau Traders", "ACTIVE")])
        res = self.client.post(f"/api/v1/employers/{employers[0]['id']}/leave/")
        self.assertEqual(res.data["status"], "DEACTIVATED")
        self.assertEqual(self.client.get("/api/v1/employers/").data, [])
        self.assertEqual(len(self.client.get("/api/v1/payslips/").data["results"]), 1)  # their pay is still theirs
        self.assertTrue(User.objects.get(pk=self.workers[0].owner_id).check_password(PASSWORD))
        self.assertEqual(Payment.objects.filter(worker__status="DEACTIVATED").count(), 1)

        # They can come back, on a new record; the old one keeps its history.
        membership = Membership.objects.select_related("organization", "user").get(user=self.owner)
        _worker, code = register.invite(membership=membership, account_number=self.workers[0].account_number,
                                        salary_amount="12000")  # fmt: skip
        self.assertEqual(self.client.post("/api/v1/worker-invitations/accept/", {"code": code}).data["status"], "ACTIVE")
        self.assertEqual(Worker.objects.filter(user=self.workers[0].owner).count(), 2)

    @mock.patch("payroll.workers.get_sms_backend")
    def test_removing_an_invitation_and_older_apps(self, sms):
        worker, code = self.invite(sms, full_name="Never Mind", phone_number="0733000000")
        self.assertEqual(self.client.delete(self.url(f"workers/{worker['id']}/")).status_code, 204)
        self.as_worker(4)
        self.assertEqual(self.client.post("/api/v1/worker-invitations/accept/", {"code": code}).status_code, 404)

        self.client.force_authenticate(self.owner)
        self.add_workers()
        active = Worker.objects.get(wallet=self.workers[1], status="ACTIVE")
        res = self.client.patch(self.url(f"workers/{active.id}/"), {"is_active": False}, format="json")  # old app
        self.assertEqual((res.data["status"], res.data["is_active"]), ("DEACTIVATED", False))
