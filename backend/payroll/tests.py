"""Payroll: workers, pay runs with approval, reversals, and each business's own books."""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting import reports
from accounting.models import BusinessEntry
from accounting.services import business_date
from audit.models import AuditEvent
from banking.models import Account, Transfer
from banking.services import open_wallet, transfer_funds
from fluxpay.testing import funded
from organizations import services as orgs
from organizations.models import Membership, Payment
from platform_settings.models import PlatformSettings

from . import workers as register
from .models import PayRun, Worker

User = get_user_model()
PASSWORD = "Str0ng-Pass!42"
D = Decimal


@funded
class PayrollTestCase(APITestCase):
    """A business (Kamau Traders) with 50,000 in its cashbook, and five FluxPay users who can become its workers."""

    def setUp(self):
        self.owner = User.objects.create_user("owner@kamau.test", PASSWORD, full_name="Grace Kamau")
        self.owner_wallet = open_wallet(self.owner)  # 1,000 welcome bonus (staff-configured promotion)
        self.org = orgs.create_organization(user=self.owner, name="Kamau Traders")
        self.business = self.org.accounts.get()
        self.finance = self.member("finance@kamau.test", "Felix Finance", Membership.Role.FINANCE)
        self.workers = []
        for i in range(5):
            user = User.objects.create_user(f"worker{i}@kamau.test", PASSWORD, full_name=f"Worker {i}",
                                            phone_number=f"07110000{i:02d}")  # fmt: skip
            self.workers.append(open_wallet(user))
        self.fund_business("50000")
        self.client.force_authenticate(self.owner)

    def member(self, email, name, role):
        user = User.objects.create_user(email, PASSWORD, full_name=name)
        Membership.objects.create(organization=self.org, user=user, role=role)
        return user

    def fund_business(self, amount):
        """The owner pays capital in from their own wallet (topped up through the platform's cashbook)."""
        Account.objects.filter(pk=self.owner_wallet.pk).update(balance=D(amount) + 1000)
        transfer_funds(
            user=self.owner, source_id=self.owner_wallet.id, destination_number=self.business.account_number,
            amount=D(amount), note="Capital for the business", idempotency_key=f"capital-{amount}",
        )  # fmt: skip

    def url(self, path=""):
        return f"/api/v1/organizations/{self.org.id}/{path}"

    def add_workers(self, salary="10000"):
        """Invites each worker by their FluxPay account, and each accepts in their own app."""
        membership = Membership.objects.select_related("organization", "user").get(organization=self.org, user=self.owner)
        for wallet in self.workers:
            _worker, code = register.invite(membership=membership, account_number=wallet.account_number,
                                            salary_amount=salary)  # fmt: skip
            self.client.force_authenticate(wallet.owner)
            res = self.client.post("/api/v1/worker-invitations/accept/", {"code": code})
            self.assertEqual(res.status_code, 200, res.data)
        self.client.force_authenticate(self.owner)

    def create_run(self, title="October salaries"):
        res = self.client.post(self.url("pay-runs/"), {"title": title, "pay_date": business_date().isoformat()})
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def balance(self, wallet):
        wallet.refresh_from_db()
        return wallet.balance


class PayrollTests(PayrollTestCase):
    """Most tests use the API, the way the app does."""

    # Workers

    def test_invite_workers_by_account_or_phone_and_import_many(self):
        res = self.client.post(self.url("workers/"), {"full_name": "Wanjiru", "phone_number": "0711000000",
                                                      "salary": "12,500"})  # fmt: skip
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(
            (res.data["name"], res.data["salary"], res.data["status"], res.data["account_number"], res.data["currency"]),
            ("Wanjiru", "12500.00", "INVITED", "", "KES"),
        )
        res = self.client.post(
            self.url("workers/import/"),
            {"rows": [
                {"account_number": self.workers[1].account_number, "salary": "9000", "job_title": "Driver"},
                {"account_number": self.workers[2].account_number, "salary": "9000"},
                {"account_number": "0000000000", "salary": "9000"},
                {"account_number": self.workers[3].account_number, "salary": "abc"},
            ]},
            format="json",
        )  # fmt: skip
        self.assertEqual((res.data["created"], len(res.data["errors"])), (2, 2))
        self.assertEqual([e["row"] for e in res.data["errors"]], [3, 4])
        self.assertEqual(self.client.get(self.url("workers/")).data["count"], 0)  # nobody has accepted yet
        self.assertEqual(self.client.get(self.url("workers/"), {"status": "INVITED"}).data["count"], 3)

    def test_csv_import(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        rows = "Account Number,Salary,Employee Number\n" + "\n".join(
            f"{w.account_number},8000,E{i}" for i, w in enumerate(self.workers)
        )
        res = self.client.post(
            self.url("workers/import/"), {"file": SimpleUploadedFile("staff.csv", rows.encode())}, format="multipart"
        )
        self.assertEqual(res.data, {"created": 5, "updated": 0, "errors": []})

    def test_unknown_accounts_and_viewers_cannot_add(self):
        res = self.client.post(self.url("workers/"), {"account_number": "1234567890", "salary": "100"})
        self.assertEqual(res.status_code, 404)
        self.assertIn("No FluxPay personal account", res.data["error"]["message"])
        viewer = self.member("viewer@kamau.test", "Vic Viewer", Membership.Role.VIEWER)
        self.client.force_authenticate(viewer)
        res = self.client.post(self.url("workers/"), {"account_number": self.workers[0].account_number, "salary": "1"})
        self.assertEqual(res.status_code, 403)

    # Pay runs

    def test_pay_run_within_threshold_pays_everyone_at_once(self):
        self.org.approval_threshold = D("100000")
        self.org.save()
        self.add_workers("10000")
        run = self.create_run()
        self.assertEqual((run["status"], run["worker_count"], run["total"]), ("DRAFT", 5, "50000.00"))
        res = self.client.post(self.url(f"pay-runs/{run['id']}/submit/"))
        self.assertEqual(res.data["status"], "PAID", res.data)
        self.assertEqual(self.balance(self.business), D("0"))
        self.assertEqual([self.balance(w) for w in self.workers], [D("11000")] * 5)  # 1,000 bonus + 10,000 pay
        self.assertEqual(Payment.objects.filter(status="COMPLETED").count(), 5)
        self.assertTrue(AuditEvent.objects.filter(action="payroll.run_paid").exists())

    def test_large_pay_run_needs_a_second_person(self):
        self.add_workers("10000")  # threshold is 0: every run needs approval
        self.client.force_authenticate(self.finance)
        run = self.create_run()
        res = self.client.post(self.url(f"pay-runs/{run['id']}/submit/"))
        self.assertEqual(res.data["status"], "PENDING_APPROVAL")
        self.assertEqual(self.balance(self.business), D("50000"))  # nothing paid yet
        res = self.client.post(self.url(f"pay-runs/{run['id']}/approve/"))
        self.assertEqual(res.status_code, 403)  # finance can't approve
        self.client.force_authenticate(self.owner)
        res = self.client.post(self.url(f"pay-runs/{run['id']}/approve/"), {"note": "Checked against timesheets"})
        self.assertEqual(res.data["status"], "PAID")
        self.assertEqual(res.data["decided_by_name"], "Grace Kamau")

    def test_nobody_approves_their_own_pay_run(self):
        self.add_workers()
        run = self.create_run()
        self.client.post(self.url(f"pay-runs/{run['id']}/submit/"))
        res = self.client.post(self.url(f"pay-runs/{run['id']}/approve/"))
        self.assertEqual(res.status_code, 403)
        self.assertIn("can't approve a pay run you prepared", res.data["error"]["message"])

    def test_not_enough_money_pays_nobody(self):
        self.org.approval_threshold = D("1000000")
        self.org.save()
        self.add_workers("10000.01")  # 50,000.05 needed, 50,000 held
        run = self.create_run()
        res = self.client.post(self.url(f"pay-runs/{run['id']}/submit/"))
        self.assertEqual(res.status_code, 400)
        self.assertIn("Add 0.05 first", res.data["error"]["message"])
        self.assertEqual(self.balance(self.business), D("50000"))
        self.assertFalse(Payment.objects.filter(status="COMPLETED").exists())
        self.assertEqual(PayRun.objects.get().status, "DRAFT")

    def test_draft_amounts_can_be_changed_and_workers_left_out(self):
        self.add_workers("10000")
        run = self.create_run()
        first, second = run["payslips"][0], run["payslips"][1]
        res = self.client.patch(self.url(f"pay-runs/{run['id']}/payslips/{first['id']}/"), {"amount": "12500"})
        self.assertEqual(res.data["total"], "52500.00")
        res = self.client.delete(self.url(f"pay-runs/{run['id']}/payslips/{second['id']}/"))
        self.assertEqual((res.data["total"], res.data["worker_count"]), ("42500.00", 4))

    # Reversals

    def paid_run(self):
        self.org.approval_threshold = D("1000000")
        self.org.save()
        self.add_workers("10000")
        run = self.create_run()
        return self.client.post(self.url(f"pay-runs/{run['id']}/submit/")).data

    def test_wrong_payment_is_taken_back(self):
        run = self.paid_run()
        payslip = run["payslips"][0]
        res = self.client.post(self.url(f"payslips/{payslip['id']}/reverse/"), {"reason": "Left the company in September"})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], "REVERSED")
        self.assertEqual(self.balance(self.business), D("10000"))
        worker = Account.objects.get(account_number=payslip["account_number"])
        self.assertEqual(worker.balance, D("1000"))
        reversal = Transfer.objects.get(reverses__reference=payslip["reference"])
        self.assertIn("Left the company", reversal.note)
        again = self.client.post(self.url(f"payslips/{payslip['id']}/reverse/"), {"reason": "Twice by mistake"})
        self.assertEqual(again.status_code, 400)

    def test_cannot_take_back_money_the_worker_already_spent(self):
        run = self.paid_run()
        payslip = run["payslips"][0]
        worker = Account.objects.get(account_number=payslip["account_number"])
        transfer_funds(
            user=worker.owner, source_id=worker.id, destination_number=self.owner_wallet.account_number,
            amount=D("10500"), note="Rent", idempotency_key="spent",
        )  # fmt: skip
        res = self.client.post(self.url(f"payslips/{payslip['id']}/reverse/"), {"reason": "Paid twice in error"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("only has 500.00 KES left", res.data["error"]["message"])
        self.assertEqual(Payment.objects.get(id=payslip["id"]).status, "COMPLETED")

    def test_reversal_window_and_who_may_reverse(self):
        run = self.paid_run()
        payslip = run["payslips"][0]
        self.client.force_authenticate(self.finance)
        res = self.client.post(self.url(f"payslips/{payslip['id']}/reverse/"), {"reason": "Paid in error"})
        self.assertEqual(res.status_code, 403)
        self.client.force_authenticate(self.owner)
        PlatformSettings.objects.update(payroll_reversal_days=3)
        later = timezone.now() + timedelta(days=4)
        with mock.patch("payroll.services.timezone.now", return_value=later):
            res = self.client.post(self.url(f"payslips/{payslip['id']}/reverse/"), {"reason": "Paid in error"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("within 3 days", res.data["error"]["message"])

    def test_cancelled_run_cancels_its_payslips(self):
        self.add_workers()
        run = self.create_run()
        self.client.delete(self.url(f"pay-runs/{run['id']}/"))
        self.assertEqual(set(Payment.objects.values_list("status", flat=True)), {"CANCELLED"})

    # Payment types

    def test_pay_run_with_an_allowance_on_top_of_salary(self):
        self.org.approval_threshold = D("1000000")
        self.org.save()
        self.add_workers("10000")
        self.fund_business("3000")
        run = self.create_run()
        worker = Worker.objects.get(wallet=self.workers[0])
        line = {"worker_id": str(worker.id), "amount": "3000", "type": "ALLOWANCE"}
        res = self.client.post(self.url(f"pay-runs/{run['id']}/payslips/"), line)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data["total"], res.data["worker_count"], len(res.data["payslips"])), ("53000.00", 5, 6))
        again = self.client.post(self.url(f"pay-runs/{run['id']}/payslips/"), line)
        self.assertEqual(again.data["error"]["code"], "duplicate_payslip")

        res = self.client.post(self.url(f"pay-runs/{run['id']}/submit/"))
        self.assertEqual(res.data["status"], "PAID", res.data)
        self.assertEqual(self.balance(self.workers[0]), D("14000"))  # 1,000 bonus + salary + allowance
        allowance = Payment.objects.get(type="ALLOWANCE")
        entry = BusinessEntry.objects.get(reference=allowance.reference)
        self.assertEqual((entry.category.name, entry.source, entry.counterparty), ("Allowances", "PAYROLL", "Worker 0"))

        self.client.force_authenticate(self.workers[0].owner)
        mine = self.client.get("/api/v1/payslips/").data["results"]
        self.assertEqual(sorted(p["type_label"] for p in mine), ["Allowance", "Salary"])
        self.assertEqual({p["status"] for p in mine}, {"PAID"})

    def test_one_off_bonus_to_a_worker(self):
        self.org.approval_threshold = D("1000000")
        self.org.save()
        self.add_workers()
        worker = Worker.objects.get(wallet=self.workers[0])
        res = self.client.post(self.url("payments/"), {
            "type": "BONUS", "worker_id": str(worker.id), "amount": "2500", "note": "Best seller in October",
            "idempotency_key": "bonus-oct-1",
        })  # fmt: skip
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data["status"], res.data["type_label"], res.data["recipient_name"]),
                         ("COMPLETED", "Bonus", "Worker 0"))  # fmt: skip
        reference = res.data["reference"]
        received = self.workers[0].transactions.get(reference=reference)  # one reference on every side
        self.assertEqual((received.amount, received.description), (D("2500"), "Best seller in October"))
        self.assertEqual(BusinessEntry.objects.get(reference=reference).category.name, "Bonuses")

        self.client.force_authenticate(self.workers[0].owner)
        mine = self.client.get("/api/v1/payslips/").data["results"]
        self.assertEqual([(p["type"], p["title"], p["status"]) for p in mine],
                         [("BONUS", "Best seller in October", "PAID")])  # fmt: skip

    def test_worker_payments_go_to_this_businesss_workers(self):
        self.add_workers()
        res = self.client.post(self.url("payments/"), {"type": "SALARY", "amount": "100", "idempotency_key": "no-worker"})
        self.assertEqual(res.status_code, 400)
        worker = Worker.objects.filter(organization=self.org).first()
        res = self.client.post(self.url("payments/"), {
            "type": "SUPPLIER", "worker_id": str(worker.id), "destination_account_number": self.workers[0].account_number,
            "amount": "100", "idempotency_key": "supplier-to-worker",
        })  # fmt: skip
        self.assertEqual(res.data["error"]["code"], "worker_not_allowed")
        other = orgs.create_organization(user=self.finance, name="Other Co")
        theirs = Worker.objects.create(organization=other, wallet=self.workers[1], user=self.workers[1].owner,
                                       full_name="Worker 1", status="ACTIVE", salary=D("1"), added_by=self.finance)  # fmt: skip
        res = self.client.post(self.url("payments/"), {
            "type": "BONUS", "worker_id": str(theirs.id), "amount": "100", "idempotency_key": "other-worker",
        })  # fmt: skip
        self.assertEqual(res.status_code, 404)

    def test_workers_see_their_payslips(self):
        run = self.paid_run()
        worker = Account.objects.get(account_number=run["payslips"][0]["account_number"]).owner
        self.client.force_authenticate(worker)
        res = self.client.get("/api/v1/payslips/")
        self.assertEqual(res.data["results"][0]["business"], "Kamau Traders")
        self.assertEqual(res.data["results"][0]["amount"], "10000.00")

    # The business's books

    def test_business_cashbook_and_books(self):
        run = self.paid_run()  # capital 50,000 in; payroll 50,000 out
        self.client.post(self.url(f"payslips/{run['payslips'][0]['id']}/reverse/"), {"reason": "Left the company"})
        customer = self.workers[1].owner  # a worker buying from the business counts as a sale
        transfer_funds(
            user=customer, source_id=self.workers[1].id, destination_number=self.business.account_number,
            amount=D("3000"), note="Order 17", idempotency_key="sale-1",
        )  # fmt: skip

        res = self.client.get(self.url("books/cashbook/"))
        entries = res.data["entries"]
        self.assertEqual(
            [(e["direction"], e["amount"], e["category"]["name"]) for e in reversed(entries)],
            [("IN", "50000.00", "Owner's capital")] + [("OUT", "10000.00", "Salaries and wages")] * 5
            + [("IN", "10000.00", "Salaries and wages"), ("IN", "3000.00", "Sales and revenue")],
        )  # fmt: skip
        self.assertEqual(entries[0]["balance"], "13000.00")
        self.assertEqual(res.data["closing_balance"], str(self.balance(self.business)))
        payroll_lines = [e for e in entries if e["source"] == "PAYROLL"]
        self.assertEqual(  # one line per worker, carrying the payslip's reference
            sorted(e["reference"] for e in payroll_lines), sorted(p["reference"] for p in run["payslips"])
        )
        self.assertEqual(entries[1]["source"], "PAYROLL_REVERSAL")

        res = self.client.get(self.url("books/summary/"))
        pl, bs = res.data["income_statement"], res.data["balance_sheet"]
        self.assertEqual((pl["income"]["total"], pl["expenses"]["total"], pl["profit"]), ("3000.00", "40000.00", "-37000.00"))
        self.assertTrue(bs["balanced"])
        self.assertEqual(bs["assets"]["total"], "13000.00")

    def test_reclassify_and_custom_categories(self):
        transfer_funds(
            user=self.workers[0].owner, source_id=self.workers[0].id, destination_number=self.business.account_number,
            amount=D("500"), note="", idempotency_key="in-1",
        )  # fmt: skip
        entry = BusinessEntry.objects.filter(organization=self.org, amount=D("500")).get()
        self.assertEqual(entry.category.name, "Sales and revenue")
        res = self.client.post(self.url("books/categories/"), {"name": "Consulting fees", "type": "INCOME"})
        self.assertEqual(res.status_code, 201)
        res = self.client.patch(self.url(f"books/entries/{entry.id}/"), {"category_id": res.data["id"]})
        self.assertEqual(res.data["category"]["name"], "Consulting fees")
        pl = reports.income_statement("KES", business_date().replace(day=1), business_date(), organization=self.org)
        self.assertEqual({r.account.name: r.amount for r in pl["income"].rows}, {"Consulting fees": D("500")})

    def test_business_books_stay_out_of_fluxpays_books(self):
        self.paid_run()
        platform_tb = reports.trial_balance("KES", business_date())
        self.assertTrue(platform_tb["balanced"])
        self.assertFalse(any(r["account"].organization_id for r in platform_tb["rows"]))
        business_tb = reports.trial_balance("KES", business_date(), organization=self.org)
        self.assertTrue(business_tb["balanced"])

    def test_only_members_see_a_business(self):
        stranger = User.objects.create_user("stranger@example.com", PASSWORD, full_name="Stranger")
        self.client.force_authenticate(stranger)
        for path in ("workers/", "pay-runs/", "books/cashbook/", "books/summary/"):
            self.assertEqual(self.client.get(self.url(path)).status_code, 404, path)

    def test_payroll_alerts_workers_but_not_200_times_to_the_business(self):
        from fluxpay.celery import app as celery_app
        from notifications.models import Notification

        conf = celery_app.conf
        saved = (conf.task_always_eager, conf.task_eager_propagates)
        conf.update(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)  # run alert jobs inline
        self.addCleanup(conf.update, CELERY_TASK_ALWAYS_EAGER=saved[0], CELERY_TASK_EAGER_PROPAGATES=saved[1])
        with self.captureOnCommitCallbacks(execute=True):
            self.paid_run()
        pay_refs = Payment.objects.values_list("reference", flat=True)
        alerts = Notification.objects.filter(reference__in=list(pay_refs))
        self.assertEqual(alerts.filter(event="transfer.received").count(), 10)  # email + SMS to each of 5 workers
        self.assertFalse(alerts.filter(event="transfer.sent").exists())  # no flood to the business


class ScaleTests(APITestCase):
    def test_two_hundred_workers_in_one_run(self):
        owner = User.objects.create_user("big@biz.test", PASSWORD, full_name="Big Boss")
        org = orgs.create_organization(user=owner, name="Big Biz")
        org.approval_threshold = D("100000000")
        org.save()
        business = org.accounts.get()
        Account.objects.filter(pk=business.pk).update(balance=D("5000000"))
        membership = Membership.objects.get(organization=org, user=owner)
        users = User.objects.bulk_create(
            User(email=f"w{i}@big.test", full_name=f"Worker {i:03d}") for i in range(200)
        )
        wallets = Account.objects.bulk_create(Account(owner=u, currency="KES") for u in users)
        Worker.objects.bulk_create(
            Worker(organization=org, wallet=w, user=w.owner, full_name=w.owner.full_name, status="ACTIVE",
                   salary=D("15000"), added_by=owner)
            for w in wallets
        )  # fmt: skip
        from . import services

        run = services.create_pay_run(membership=membership, title="Big payroll", pay_date=business_date())
        services.submit_pay_run(membership=membership, run_id=run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, "PAID")
        self.assertEqual(Payment.objects.filter(pay_run=run, status="COMPLETED").count(), 200)
        business.refresh_from_db()
        self.assertEqual(business.balance, D("2000000"))
        self.assertEqual(BusinessEntry.objects.filter(organization=org, source="PAYROLL").count(), 200)
