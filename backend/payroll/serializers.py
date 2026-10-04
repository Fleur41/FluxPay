from decimal import Decimal

from django.db.models import Count, Sum
from rest_framework import serializers

from accounting.models import BusinessEntry, LedgerAccount

from .models import PayRun, Payslip, Worker


class WorkerSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="wallet.owner.full_name", read_only=True)
    account_number = serializers.CharField(source="wallet.account_number", read_only=True)
    currency = serializers.CharField(source="wallet.currency", read_only=True)

    class Meta:
        model = Worker
        fields = ("id", "name", "account_number", "currency", "employee_number", "job_title", "salary", "is_active",
                  "created_at")  # fmt: skip


class WorkerCreateSerializer(serializers.Serializer):
    account_number = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    salary = serializers.CharField(max_length=20)  # "12,500" is fine: payroll.services parses it
    employee_number = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    job_title = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")

    def validate(self, data):
        if not data["account_number"] and not data["phone_number"]:
            raise serializers.ValidationError("Give the worker's FluxPay account number or phone number.")
        return data


class WorkerUpdateSerializer(serializers.Serializer):
    salary = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False)
    employee_number = serializers.CharField(max_length=30, required=False, allow_blank=True)
    job_title = serializers.CharField(max_length=80, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class WorkerImportSerializer(serializers.Serializer):
    """Either `rows` (JSON) or `file` (a CSV with columns account_number/phone_number, salary, ...)."""

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
    worker_id = serializers.UUIDField(source="worker.id", read_only=True)
    worker_name = serializers.CharField(source="worker.name", read_only=True)
    account_number = serializers.CharField(source="worker.wallet.account_number", read_only=True)
    employee_number = serializers.CharField(source="worker.employee_number", read_only=True)
    job_title = serializers.CharField(source="worker.job_title", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    reference = serializers.CharField(source="transfer.reference", read_only=True, default=None)
    reversal_reference = serializers.CharField(source="reversal.reference", read_only=True, default=None)

    class Meta:
        model = Payslip
        fields = ("id", "worker_id", "worker_name", "account_number", "employee_number", "job_title", "amount",
                  "status", "status_label", "reference", "reversal_reference", "reversed_at", "reversal_reason")  # fmt: skip


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
        return str(self._totals(run).get(Payslip.Status.REVERSED, {}).get("amount") or "0.00")

    def get_worker_count(self, run):
        return sum(r["count"] for r in self._totals(run).values())

    def get_reversed_count(self, run):
        return self._totals(run).get(Payslip.Status.REVERSED, {}).get("count") or 0


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


class ReverseSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=200)


class MyPayslipSerializer(serializers.ModelSerializer):
    business = serializers.CharField(source="pay_run.organization.name", read_only=True)
    title = serializers.CharField(source="pay_run.title", read_only=True)
    pay_date = serializers.DateField(source="pay_run.pay_date", read_only=True)
    currency = serializers.CharField(source="worker.wallet.currency", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    reference = serializers.CharField(source="transfer.reference", read_only=True, default=None)

    class Meta:
        model = Payslip
        fields = ("id", "business", "title", "pay_date", "amount", "currency", "status", "status_label", "reference",
                  "reversal_reason")  # fmt: skip


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
