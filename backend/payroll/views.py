"""Payroll and business-books API, scoped to one business (organizations.services.membership_for)."""

from datetime import date as Date

from django.conf import settings
from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounting import business as books
from accounting import invoices, reports
from accounting.business_reconciliation import reconcile as reconcile_business
from accounting.models import BusinessEntry, Invoice, LedgerAccount
from accounting.services import business_date
from banking.models import Account
from fluxpay.exceptions import BusinessError
from organizations.models import Payment
from organizations.roles import Perm
from organizations.serializers import DecisionSerializer
from organizations.views import OrgScopedMixin

from . import services
from . import workers as register
from .models import PayRun, Worker
from .serializers import (
    BookEntrySerializer,
    CategoryCreateSerializer,
    CategorySerializer,
    CodeSerializer,
    EmployerSerializer,
    InvoiceCancelSerializer,
    InvoiceCreateSerializer,
    InvoicePaySerializer,
    InvoiceSerializer,
    MyPayslipSerializer,
    PayRunCreateSerializer,
    PayRunDetailSerializer,
    PayRunSerializer,
    PayslipCreateSerializer,
    PayslipSerializer,
    PayslipUpdateSerializer,
    ReclassifySerializer,
    ReverseSerializer,
    WorkerActionSerializer,
    WorkerCreateSerializer,
    WorkerImportSerializer,
    WorkerSerializer,
    WorkerUpdateSerializer,
)


class WritesNeedPayments(OrgScopedMixin):
    """Reads need membership; changes need a role that may make payments (owner, admin, finance)."""

    def perm_for(self, request):
        return Perm.VIEW if request.method == "GET" else Perm.INITIATE_PAYMENT


# --- Workers ------------------------------------------------------------------------------------


class WorkersNeedManage(OrgScopedMixin):
    def perm_for(self, request):
        return Perm.VIEW if request.method == "GET" else Perm.MANAGE_WORKERS


class WorkerListCreateView(WorkersNeedManage, generics.ListAPIView):
    """GET: active workers by default; ?status=INVITED|PENDING_ACTIVATION|SUSPENDED|DEACTIVATED, or ?active=all.
    POST: invites a worker (they join once they accept)."""

    serializer_class = WorkerSerializer

    def get_queryset(self):
        workers = Worker.objects.select_related("wallet__owner").filter(organization_id=self.membership.organization_id)
        params = self.request.query_params
        if params.get("status"):
            workers = workers.filter(status=params["status"])
        elif params.get("active", "true") != "all":
            workers = workers.filter(status=Worker.Status.ACTIVE)
        if search := params.get("search", "").strip():
            workers = workers.filter(
                Q(full_name__icontains=search)
                | Q(wallet__owner__full_name__icontains=search)
                | Q(wallet__account_number__startswith=search)
                | Q(phone_number__contains=search)
                | Q(employee_number__iexact=search)
                | Q(job_title__icontains=search)
            )
        return workers

    def post(self, request, org_id):
        serializer = WorkerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        worker, _code = register.invite(membership=self.membership, salary_amount=data.pop("salary"), **data)
        return Response(WorkerSerializer(worker).data, status=status.HTTP_201_CREATED)


class WorkerImportView(WorkersNeedManage, APIView):
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def post(self, request, org_id):
        serializer = WorkerImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = register.import_workers(membership=self.membership, rows=serializer.validated_data["rows"])
        return Response(result)


class WorkerDetailView(WorkersNeedManage, APIView):
    def get(self, request, org_id, worker_id):
        return Response(WorkerSerializer(register.get(self.membership, worker_id)).data)

    def patch(self, request, org_id, worker_id):
        serializer = WorkerUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        register.update(membership=self.membership, worker_id=worker_id, **serializer.validated_data)
        return Response(WorkerSerializer(register.get(self.membership, worker_id)).data)

    def delete(self, request, org_id, worker_id):
        """Removes the worker (or cancels the invitation or request); their pay history stays."""
        register.deactivate(membership=self.membership, worker_id=worker_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkerActionView(OrgScopedMixin, APIView):
    """POST .../workers/<id>/{approve,decline,suspend,reactivate,resend-invitation}/"""

    ACTIONS = {
        "approve": Perm.APPROVE_WORKER,
        "decline": Perm.APPROVE_WORKER,
        "suspend": Perm.MANAGE_WORKERS,
        "reactivate": Perm.MANAGE_WORKERS,
        "resend-invitation": Perm.MANAGE_WORKERS,
    }

    def perm_for(self, request):
        perm = self.ACTIONS.get(self.kwargs["action"])
        if perm is None:
            raise BusinessError("Unknown action.", "not_found", status.HTTP_404_NOT_FOUND)
        return perm

    def post(self, request, org_id, worker_id, action):
        serializer = WorkerActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data, ids = serializer.validated_data, {"membership": self.membership, "worker_id": worker_id}
        if action == "approve":
            if "salary" not in data:
                raise BusinessError("Enter the worker's salary.", "salary_required")
            worker = register.approve(**ids, salary_amount=data["salary"], job_title=data["job_title"],
                                      employee_number=data["employee_number"])  # fmt: skip
        elif action == "decline":
            worker = register.decline(**ids, reason=data["reason"])
        elif action == "suspend":
            worker = register.suspend(**ids, reason=data["reason"])
        elif action == "reactivate":
            worker = register.reactivate(**ids)
        else:
            worker, _code = register.resend_invitation(**ids)
        return Response(WorkerSerializer(worker).data)


class JoinCodeView(OrgScopedMixin, APIView):
    """GET/POST/DELETE .../worker-join-code/ — the code (and QR link) workers use to ask to join.

    POST makes a new code (the old one stops working); DELETE switches joining by code off.
    """

    perm = Perm.APPROVE_WORKER

    def get(self, request, org_id):
        return Response(self.body(self.membership.organization.worker_join_code))

    def post(self, request, org_id):
        organization = register.set_join_code(membership=self.membership, enabled=True)
        return Response(self.body(organization.worker_join_code), status=status.HTTP_201_CREATED)

    def delete(self, request, org_id):
        register.set_join_code(membership=self.membership, enabled=False)
        return Response(self.body(None))

    @staticmethod
    def body(code):
        if not code:
            return {"enabled": False, "code": None, "link": None}
        return {"enabled": True, "code": register.display_code(code),
                "link": settings.WORKER_JOIN_LINK.format(code=code)}  # fmt: skip


# --- The worker's own side ------------------------------------------------------------------------


class CodeThrottled(APIView):
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "worker_codes"


class InvitationPreviewView(CodeThrottled):
    """POST /worker-invitations/preview/ {code} — who invited you, before you accept."""

    def post(self, request):
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        worker = register.preview_invitation(serializer.validated_data["code"])
        return Response({"business": worker.organization.name, "name": worker.full_name,
                         "job_title": worker.job_title, "expires_at": worker.invite_expires_at})  # fmt: skip


class InvitationAcceptView(CodeThrottled):
    """POST /worker-invitations/accept/ {code} — you start being paid by the business, into your own wallet."""

    def post(self, request):
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        worker = register.accept_invitation(user=request.user, code=serializer.validated_data["code"])
        return Response(EmployerSerializer(worker).data)


class JoinRequestView(CodeThrottled):
    """POST /employers/join/ {code} — ask to join a business with its join code (typed, or scanned from its QR)."""

    def post(self, request):
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        worker = register.request_to_join(user=request.user, join_code=serializer.validated_data["code"])
        return Response(EmployerSerializer(worker).data, status=status.HTTP_201_CREATED)


class MyEmployersView(generics.ListAPIView):
    """GET /employers/ — the businesses you work for, have asked to join, or are invited to by your account."""

    serializer_class = EmployerSerializer
    pagination_class = None

    def get_queryset(self):
        return Worker.objects.select_related("organization", "wallet").filter(
            user=self.request.user, status__in=Worker.OPEN
        )


class LeaveEmployerView(APIView):
    """POST /employers/<id>/leave/ — stop working for a business. Your FluxPay account stays yours."""

    def post(self, request, worker_id):
        return Response(EmployerSerializer(register.leave(user=request.user, worker_id=worker_id)).data)


# --- Pay runs -----------------------------------------------------------------------------------


class PayRunListCreateView(WritesNeedPayments, generics.ListAPIView):
    serializer_class = PayRunSerializer

    def get_queryset(self):
        runs = PayRun.objects.select_related("source_account", "created_by", "decided_by").filter(
            organization_id=self.membership.organization_id
        )
        if status_filter := self.request.query_params.get("status"):
            runs = runs.filter(status=status_filter)
        return runs

    def post(self, request, org_id):
        serializer = PayRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = services.create_pay_run(membership=self.membership, **serializer.validated_data)
        return Response(PayRunDetailSerializer(run).data, status=status.HTTP_201_CREATED)


class PayRunDetailView(WritesNeedPayments, APIView):
    def get(self, request, org_id, run_id):
        return Response(PayRunDetailSerializer(services._run(self.membership, run_id)).data)

    def delete(self, request, org_id, run_id):
        run = services.cancel_pay_run(membership=self.membership, run_id=run_id)
        return Response(PayRunSerializer(run).data)


class PayslipAddView(WritesNeedPayments, APIView):
    """POST .../pay-runs/<id>/payslips/ — an extra line in a draft run, e.g. an allowance or a bonus."""

    def post(self, request, org_id, run_id):
        serializer = PayslipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        run = services.add_payslip(
            membership=self.membership, run_id=run_id, worker_id=data["worker_id"], amount=data["amount"],
            type_=data["type"],
        )  # fmt: skip
        return Response(PayRunDetailSerializer(run).data, status=status.HTTP_201_CREATED)


class PayslipEditView(WritesNeedPayments, APIView):
    def patch(self, request, org_id, run_id, payslip_id):
        serializer = PayslipUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = services.update_payslip(
            membership=self.membership, run_id=run_id, payslip_id=payslip_id, amount=serializer.validated_data["amount"]
        )
        return Response(PayRunDetailSerializer(run).data)

    def delete(self, request, org_id, run_id, payslip_id):
        run = services.update_payslip(membership=self.membership, run_id=run_id, payslip_id=payslip_id, remove=True)
        return Response(PayRunDetailSerializer(run).data)


class PayRunActionView(OrgScopedMixin, APIView):
    ACTIONS = {"submit": Perm.INITIATE_PAYMENT, "approve": Perm.APPROVE_PAYMENT, "reject": Perm.APPROVE_PAYMENT}

    def perm_for(self, request):
        perm = self.ACTIONS.get(self.kwargs["action"])
        if perm is None:
            raise BusinessError("Unknown action.", "not_found", status.HTTP_404_NOT_FOUND)
        return perm

    def post(self, request, org_id, run_id, action):
        note = DecisionSerializer(data=request.data)
        note.is_valid(raise_exception=True)
        if action == "submit":
            run = services.submit_pay_run(membership=self.membership, run_id=run_id)
        elif action == "approve":
            run = services.approve_pay_run(membership=self.membership, run_id=run_id, note=note.validated_data["note"])
        else:
            run = services.reject_pay_run(membership=self.membership, run_id=run_id, note=note.validated_data["note"])
        return Response(PayRunDetailSerializer(run).data)


class PayslipReverseView(OrgScopedMixin, APIView):
    perm = Perm.APPROVE_PAYMENT

    def post(self, request, org_id, payslip_id):
        serializer = ReverseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payslip = services.reverse_payslip(
            membership=self.membership, payslip_id=payslip_id, reason=serializer.validated_data["reason"]
        )
        return Response(PayslipSerializer(payslip).data)


class MyPayslipListView(generics.ListAPIView):
    """A worker's own pay (salaries, allowances, bonuses...) from every business that pays them through FluxPay.

    Only payments to them as a worker: what a business pays them for anything else isn't pay.
    """

    serializer_class = MyPayslipSerializer

    def get_queryset(self):
        return (
            Payment.objects.select_related("organization", "pay_run", "worker__wallet")
            .filter(
                worker__wallet__owner=self.request.user,
                status__in=[Payment.Status.COMPLETED, Payment.Status.REVERSED],
            )
            .order_by("-completed_at")
        )


# --- Business books -----------------------------------------------------------------------------


def _period(request) -> tuple[Date, Date]:
    today = business_date()
    start = parse_date(request.query_params.get("start") or "") or today.replace(day=1)
    end = parse_date(request.query_params.get("end") or "") or today
    if start > end:
        raise BusinessError("The start date must be before the end date.", "invalid_period")
    return start, end


def _wallet(membership, wallet_id=None) -> Account:
    wallets = Account.objects.select_related("organization").filter(organization_id=membership.organization_id)
    wallet = wallets.filter(id=wallet_id).first() if wallet_id else wallets.order_by("created_at").first()
    if wallet is None:
        raise BusinessError("Business wallet not found.", "account_not_found", status.HTTP_404_NOT_FOUND)
    return wallet


class CashbookView(OrgScopedMixin, APIView):
    def get(self, request, org_id):
        wallet = _wallet(self.membership, request.query_params.get("wallet"))
        start, end = _period(request)
        data = books.cashbook(self.membership.organization, wallet, start, end)
        rows = []
        for row in reversed(data["rows"]):  # newest first, like a statement
            item = BookEntrySerializer(row["entry"]).data
            item["balance"] = str(row["balance"])
            rows.append(item)
        return Response(
            {
                "wallet": {"id": str(wallet.id), "account_number": wallet.account_number, "currency": wallet.currency,
                           "balance": str(wallet.balance)},
                "start": start, "end": end,
                "opening_balance": str(data["opening"]), "money_in": str(data["money_in"]),
                "money_out": str(data["money_out"]), "closing_balance": str(data["closing"]),
                "entries": rows,
            }
        )  # fmt: skip


class BooksSummaryView(OrgScopedMixin, APIView):
    """Profit and loss for a period, and the balance sheet at its end, from the business's own books."""

    def get(self, request, org_id):
        organization = self.membership.organization
        wallet = _wallet(self.membership)
        start, end = _period(request)
        books.categories(organization, wallet.currency)  # so an empty business still shows its categories
        pl = reports.income_statement(wallet.currency, start, end, organization=organization)
        bs = reports.balance_sheet(wallet.currency, end, organization=organization)

        def lines(section):
            rows = [{"code": r.account.code, "name": r.account.name, "amount": str(r.amount)} for r in section.rows]
            rows += [{"code": "", "name": name, "amount": str(amount)} for name, amount in section.extra]
            return {"title": section.title, "lines": rows, "total": str(section.total)}

        return Response(
            {
                "currency": wallet.currency, "start": start, "end": end,
                "income_statement": {"income": lines(pl["income"]), "expenses": lines(pl["expenses"]),
                                     "profit": str(pl["profit"])},
                "balance_sheet": {"assets": lines(bs["assets"]), "liabilities": lines(bs["liabilities"]),
                                  "equity": lines(bs["equity"]), "balanced": bs["balanced"]},
            }
        )  # fmt: skip


class CategoryListCreateView(OrgScopedMixin, APIView):
    def perm_for(self, request):
        return Perm.VIEW if request.method == "GET" else Perm.INITIATE_PAYMENT

    def get(self, request, org_id):
        wallet = _wallet(self.membership)
        return Response(CategorySerializer(books.categories(self.membership.organization, wallet.currency), many=True).data)

    def post(self, request, org_id):
        serializer = CategoryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wallet = _wallet(self.membership)
        account = books.add_category(
            organization=self.membership.organization, currency=wallet.currency,
            name=serializer.validated_data["name"], type_=serializer.validated_data["type"], actor=request.user,
        )  # fmt: skip
        return Response(CategorySerializer(account).data, status=status.HTTP_201_CREATED)


class ReconciliationView(OrgScopedMixin, APIView):
    """GET .../books/reconciliation/ — do the cashbook, ledger, payments and payouts all match? (see
    accounting.business_reconciliation). Members who can see the books can see this."""

    def get(self, request, org_id):
        return Response(reconcile_business(self.membership.organization))


class BookEntryView(OrgScopedMixin, APIView):
    perm = Perm.INITIATE_PAYMENT

    def patch(self, request, org_id, entry_id):
        serializer = ReclassifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = BusinessEntry.objects.filter(id=entry_id, organization_id=org_id).first()
        category = LedgerAccount.objects.filter(
            id=serializer.validated_data["category_id"], organization_id=org_id
        ).first()
        if entry is None or category is None:
            raise BusinessError("Entry or category not found.", "not_found", status.HTTP_404_NOT_FOUND)
        entry = books.reclassify(entry=entry, new_category=category, actor=request.user,
                                 note=serializer.validated_data["note"])  # fmt: skip
        return Response(BookEntrySerializer(entry).data)


# --- Bills (payables) and invoices (receivables) ---------------------------------------------------


class InvoiceListCreateView(WritesNeedPayments, APIView):
    """GET .../books/invoices/?kind=BILL|INVOICE&open=1 — with what's still owed each way.
    POST — records a bill or invoice (owners, admins, finance)."""

    def get(self, request, org_id):
        organization = self.membership.organization
        wallet = _wallet(self.membership)
        items = Invoice.objects.filter(organization=organization).select_related("category", "created_by")
        kind = request.query_params.get("kind")
        if kind in Invoice.Kind.values:
            items = items.filter(kind=kind)
        if request.query_params.get("open"):
            items = items.filter(status__in=(Invoice.Status.OPEN, Invoice.Status.PART_PAID))
        totals = {k: str(v) for k, v in invoices.totals(organization, wallet.currency).items()}
        return Response({"currency": wallet.currency, "totals": totals,
                         "results": InvoiceSerializer(items[:200], many=True).data})  # fmt: skip

    def post(self, request, org_id):
        serializer = InvoiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        wallet = _wallet(self.membership)
        category = LedgerAccount.objects.filter(id=data["category_id"], organization_id=org_id).first()
        if category is None:
            raise BusinessError("Category not found.", "not_found", status.HTTP_404_NOT_FOUND)
        invoice = invoices.create(
            organization=self.membership.organization, kind=data["kind"], party=data["party"], amount=data["amount"],
            category=category, currency=wallet.currency, actor=request.user, description=data["description"],
            issue_date=data["issue_date"], due_date=data["due_date"],
        )  # fmt: skip
        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


class InvoiceMixin(WritesNeedPayments):
    def invoice(self, invoice_id) -> Invoice:
        invoice = Invoice.objects.filter(id=invoice_id, organization_id=self.membership.organization_id).first()
        if invoice is None:
            raise BusinessError("Bill or invoice not found.", "not_found", status.HTTP_404_NOT_FOUND)
        return invoice


class InvoiceDetailView(InvoiceMixin, APIView):
    def get(self, request, org_id, invoice_id):
        return Response(InvoiceSerializer(self.invoice(invoice_id)).data)


class InvoicePayableEntriesView(InvoiceMixin, APIView):
    """GET — the cashbook entries that could pay this bill (or collect this invoice), newest first."""

    def get(self, request, org_id, invoice_id):
        entries = invoices.payable_entries(self.invoice(invoice_id))[:50]
        return Response(BookEntrySerializer(entries, many=True).data)


class InvoicePayView(InvoiceMixin, APIView):
    """POST {entry_id} — this cashbook entry pays the bill (or collects the invoice)."""

    def post(self, request, org_id, invoice_id):
        serializer = InvoicePaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = self.invoice(invoice_id)
        entry = BusinessEntry.objects.filter(id=serializer.validated_data["entry_id"], organization_id=org_id).first()
        if entry is None:
            raise BusinessError("Cashbook entry not found.", "entry_not_found", status.HTTP_404_NOT_FOUND)
        return Response(InvoiceSerializer(invoices.pay(invoice=invoice, entry=entry, actor=request.user)).data)


class InvoiceCancelView(InvoiceMixin, APIView):
    def post(self, request, org_id, invoice_id):
        serializer = InvoiceCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = invoices.cancel(invoice=self.invoice(invoice_id), actor=request.user,
                                  reason=serializer.validated_data["reason"])  # fmt: skip
        return Response(InvoiceSerializer(invoice).data)
