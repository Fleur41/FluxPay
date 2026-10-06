from django.contrib import admin
from django.db.models import Count, Q, Sum
from unfold.admin import TabularInline
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display

from fluxpay.admin_base import StaffViewAuditMixin, ViewOnlyAdmin, admin_link, money
from organizations.models import Payment

from .models import PayRun, Worker


@admin.register(Worker)
class WorkerAdmin(StaffViewAuditMixin, ViewOnlyAdmin):
    """Businesses manage their own workers in the app; staff can look them up here."""

    list_display = ("name", "business", "wallet_link", "job_title", "salary_display", "status_label", "created_at")
    list_filter = ("status", "organization")
    search_fields = ("full_name", "wallet__owner__full_name", "wallet__account_number", "phone_number",
                     "employee_number", "organization__name")  # fmt: skip
    search_help_text = "Search by worker name, wallet number, phone, employee number or business"
    exclude = ("invite_code_hash",)
    list_select_related = ("wallet__owner", "organization")

    @display(description="Worker", ordering="wallet__owner__full_name")
    def name(self, worker):
        return worker.name

    @display(description="Business", ordering="organization__name")
    def business(self, worker):
        return admin_link("admin:organizations_organization_change", worker.organization_id, worker.organization.name)

    @display(description="Wallet")
    def wallet_link(self, worker):
        if not worker.wallet_id:
            return "-"
        return admin_link("admin:banking_account_change", worker.wallet_id, worker.wallet.account_number)

    @display(description="Salary", ordering="salary")
    def salary_display(self, worker):
        return money(worker.salary, worker.wallet.currency if worker.wallet_id else "")

    @display(
        description="Status",
        label={"ACTIVE": "success", "INVITED": "info", "PENDING_ACTIVATION": "warning", "SUSPENDED": "warning",
               "DEACTIVATED": ""},
    )  # fmt: skip
    def status_label(self, worker):
        return worker.status, worker.get_status_display()


class PayslipInline(TabularInline):
    model = Payment
    fk_name = "pay_run"
    extra = 0
    can_delete = False
    fields = ("worker_name", "account", "type", "amount", "status_label", "reference", "reversal_reason")
    readonly_fields = fields
    verbose_name_plural = "Payslips"
    per_page = 50

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("worker__wallet__owner")

    @display(description="Worker")
    def worker_name(self, payslip):
        return payslip.worker.name

    @display(description="Wallet")
    def account(self, payslip):
        return payslip.worker.wallet.account_number

    @display(
        description="Status",
        label={"COMPLETED": "success", "PENDING": "info", "REVERSED": "danger", "CANCELLED": "", "REJECTED": ""},
    )
    def status_label(self, payslip):
        return payslip.status, payslip.get_status_display()


@admin.register(PayRun)
class PayRunAdmin(StaffViewAuditMixin, ViewOnlyAdmin):
    list_display = ("title", "business", "pay_date", "status_label", "workers", "total_display", "reversed",
                    "paid_at")  # fmt: skip
    list_filter = ("status", "organization", ("pay_date", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("title", "organization__name")
    list_select_related = ("organization", "source_account")
    inlines = (PayslipInline,)
    exclude = ("book_entry",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            n=Count("payslips"),
            amount=Sum("payslips__amount"),
            reversed_n=Count("payslips", filter=Q(payslips__status="REVERSED")),
        )

    @display(description="Business", ordering="organization__name")
    def business(self, run):
        return admin_link("admin:organizations_organization_change", run.organization_id, run.organization.name)

    @display(
        description="Status",
        label={"DRAFT": "info", "PENDING_APPROVAL": "warning", "PAID": "success", "REJECTED": "danger", "CANCELLED": ""},
    )
    def status_label(self, run):
        return run.status, run.get_status_display()

    @display(description="Workers", ordering="n")
    def workers(self, run):
        return run.n

    @display(description="Total", ordering="amount")
    def total_display(self, run):
        return money(run.amount, run.source_account.currency)

    @display(description="Reversed")
    def reversed(self, run):
        return run.reversed_n or "-"
