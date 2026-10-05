from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import serializers

from accounting.models import BusinessEntry, LedgerAccount
from organizations.models import Payment

from .models import PayRun, Worker

# The payslip API kept its original words for a payment's status: a paid payslip is "PAID".
PAYSLIP_STATUS = {Payment.Status.COMPLETED: "PAID"}


class PayslipStatusField(serializers.CharField):
    def to_representation(self, value):
        return PAYSLIP_STATUS.get(value, value)


class WorkerSerializer(serializers.ModelSerializer):
    """`account_number` is empty, never null, until the worker joins (older apps expect a string); `currency` is
    the business's until then, so an invitation's salary still shows its currency."""

    name = serializers.CharField(read_only=True)
    account_number = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Worker
        fields = ("id", "name", "account_number", "currency", "phone_number", "email", "employee_number", "job_title",
                  "salary", "status", "status_label", "status_note", "is_active", "invite_expires_at", "activated_at",
                  "created_at")  # fmt: skip

    def get_account_number(self, worker) -> str:
        return worker.wallet.account_number if worker.wallet_id else ""

    def get_currency(self, worker) -> str:
        if worker.wallet_id:
            return worker.wallet.currency
        cashbook = worker.organization.accounts.first()  # a business has exactly one
        return cashbook.currency if cashbook else ""


class WorkerCreateSerializer(serializers.Serializer):
    """An invitation: by FluxPay account number, or by phone (with a name, and optionally an email)."""

    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    account_number = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    salary = serializers.CharField(max_length=20)  # "12,500" is fine: payroll.workers parses it
    employee_number = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    job_title = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")

    def validate(self, data):
        if not data["account_number"] and not data["phone_number"]:
            raise serializers.ValidationError("Give the worker's phone number or FluxPay account number.")
        return data


class WorkerUpdateSerializer(serializers.Serializer):
    salary = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False)
    employee_number = serializers.CharField(max_length=30, required=False, allow_blank=True)
    job_title = serializers.CharField(max_length=80, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)  # older apps: False removes, True reactivates


class WorkerActionSerializer(serializers.Serializer):
    """approve: salary (required), job_title, employee_number. decline, suspend, remove: reason."""

    salary = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False)
    job_title = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    employee_number = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class CodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20)


class EmployerSerializer(serializers.ModelSerializer):
    """A worker's own view of a business they work for (or are invited to, or asked to join)."""

    business = serializers.CharField(source="organization.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    account_number = serializers.SerializerMethodField()

    class Meta:
        model = Worker
        fields = ("id", "business", "job_title", "employee_number", "status", "status_label", "account_number",
                  "activated_at", "created_at")  # fmt: skip

    def get_account_number(self, worker) -> str:
        return worker.wallet.account_number if worker.wallet_id else ""


class WorkerImportSerializer(serializers.Serializer):
    """Either `rows` (JSON) or `file` (a CSV with columns account_number or phone_number and full_name, salary, ...)."""

    rows = serializers.ListField(child=serializers.DictField(), required=False, max_length=5000)
    file = serializers.FileField(required=False)

    def validate(self, data):
        if data.get("file"):
            import csv
            import io

            text = data["file"].read().decode("utf-8-sig", errors="replace")
            data["rows"] = [
                {k.strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items() if k}
                for row in csv.DictReader(io.StringIO(text))
            ]
        if not data.get("rows"):
            raise serializers.ValidationError("Send rows or a CSV file with at least one worker.")
        if len(data["rows"]) > 5000:
            raise serializers.ValidationError("Import at most 5,000 workers at a time.")
        return data


class PayslipSerializer(serializers.ModelSerializer):
    """One line of a pay run (a business payment to a worker)."""

    worker_id = serializers.UUIDField(source="worker.id", read_only=True)
    worker_name = serializers.CharField(source="worker.name", read_only=True)
    account_number = serializers.CharField(source="worker.wallet.account_number", read_only=True)
    employee_number = serializers.CharField(source="worker.employee_number", read_only=True)
    job_title = serializers.CharField(source="worker.job_title", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    status = PayslipStatusField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    reversal_reference = serializers.CharField(source="reversal.reference", read_only=True, default=None)

    class Meta:
        model = Payment
        fields = ("id", "worker_id", "worker_name", "account_number", "employee_number", "job_title", "type",
                  "type_label", "amount", "status", "status_label", "reference", "reversal_reference", "reversed_at",
                  "reversal_reason")  # fmt: skip


class PayRunSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    currency = serializers.CharField(source="source_account.currency", read_only=True)
    source_account_number = serializers.CharField(source="source_account.account_number", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    decided_by_name = serializers.CharField(source="decided_by.full_name", read_only=True, default=None)
    total = serializers.SerializerMethodField()
    reversed_total = serializers.SerializerMethodField()
    worker_count = serializers.SerializerMethodField()
    reversed_count = serializers.SerializerMethodField()

    class Meta:
        model = PayRun
        fields = ("id", "title", "pay_date", "status", "status_label", "currency", "source_account_number", "total",
                  "reversed_total", "worker_count", "reversed_count", "created_by_name", "decided_by_name",
                  "decision_note", "submitted_at", "paid_at", "created_at")  # fmt: skip

    def _totals(self, run):
        if not hasattr(run, "_totals"):
            rows = run.payslips.values("status").annotate(amount=Sum("amount"), count=Count("id"))
            run._totals = {r["status"]: r for r in rows}
        return run._totals

    def get_total(self, run):
        return str(sum((r["amount"] for r in self._totals(run).values()), Decimal("0.00")))

    def get_reversed_total(self, run):
        return str(self._totals(run).get(Payment.Status.REVERSED, {}).get("amount") or "0.00")

    def get_worker_count(self, run):
        # A worker can have several lines (salary and allowance); count people.
        return run.payslips.values("worker").distinct().count()

    def get_reversed_count(self, run):
        return self._totals(run).get(Payment.Status.REVERSED, {}).get("count") or 0


class PayRunDetailSerializer(PayRunSerializer):
    payslips = serializers.SerializerMethodField()

    class Meta(PayRunSerializer.Meta):
        fields = PayRunSerializer.Meta.fields + ("payslips",)

    def get_payslips(self, run):
        payslips = run.payslips.select_related("worker__wallet__owner", "transfer", "reversal")
        return PayslipSerializer(payslips, many=True).data


class PayRunCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=80)
    pay_date = serializers.DateField()
    source_account_id = serializers.UUIDField(required=False)
    worker_ids = serializers.ListField(child=serializers.UUIDField(), required=False)


class PayslipUpdateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))


class PayslipCreateSerializer(serializers.Serializer):
    worker_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    type = serializers.ChoiceField(choices=[(t.value, t.label) for t in Payment.WORKER_TYPES])


class ReverseSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=200)


class MyPayslipSerializer(serializers.ModelSerializer):
    """A worker's view of one payment from a business: pay-run pay, or a one-off salary, bonus..."""

    business = serializers.CharField(source="organization.name", read_only=True)
    title = serializers.SerializerMethodField()
    pay_date = serializers.SerializerMethodField()
    currency = serializers.CharField(source="worker.wallet.currency", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    status = PayslipStatusField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Payment
        fields = ("id", "business", "title", "pay_date", "type", "type_label", "amount", "currency", "status",
                  "status_label", "reference", "reversal_reason")  # fmt: skip

    def get_title(self, payment) -> str:
        return payment.pay_run.title if payment.pay_run_id else payment.note or payment.get_type_display()

    def get_pay_date(self, payment):
        return payment.pay_run.pay_date if payment.pay_run_id else timezone.localdate(payment.completed_at)


# --- Business books ----------------------------------------------------------------------------


class CategorySerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = LedgerAccount
        fields = ("id", "code", "name", "type", "type_label")


class CategoryCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    type = serializers.ChoiceField(choices=[LedgerAccount.Type.INCOME, LedgerAccount.Type.EXPENSE])


class BookEntrySerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    direction_label = serializers.CharField(source="get_direction_display", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = BusinessEntry
        fields = ("id", "date", "direction", "direction_label", "amount", "counterparty", "counterparty_account",
                  "description", "reference", "source", "source_label", "category")  # fmt: skip


class ReclassifySerializer(serializers.Serializer):
    category_id = serializers.IntegerField()
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
