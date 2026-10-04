"""Payroll and business-books API, scoped to one business (organizations.services.membership_for)."""

from datetime import date as Date

from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting import business as books
from accounting import reports
from accounting.models import BusinessEntry, LedgerAccount
from accounting.services import business_date
from banking.models import Account
from fluxpay.exceptions import BusinessError
from organizations.models import Payment
from organizations.roles import Perm
from organizations.serializers import DecisionSerializer
from organizations.views import OrgScopedMixin

from . import services
from .models import PayRun, Worker
from .serializers import (
    BookEntrySerializer,
    CategoryCreateSerializer,
    CategorySerializer,
    MyPayslipSerializer,
    PayRunCreateSerializer,
    PayRunDetailSerializer,
    PayRunSerializer,
    PayslipCreateSerializer,
    PayslipSerializer,
    PayslipUpdateSerializer,
    ReclassifySerializer,
    ReverseSerializer,
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


class WorkerListCreateView(WritesNeedPayments, generics.ListAPIView):
    serializer_class = WorkerSerializer

    def get_queryset(self):
        workers = Worker.objects.select_related("wallet__owner").filter(organization_id=self.membership.organization_id)
        if self.request.query_params.get("active", "true") != "all":
            workers = workers.filter(is_active=True)
        if search := self.request.query_params.get("search", "").strip():
            workers = workers.filter(
                Q(wallet__owner__full_name__icontains=search)
                | Q(wallet__account_number__startswith=search)
                | Q(employee_number__iexact=search)
                | Q(job_title__icontains=search)
            )
        return workers

    def post(self, request, org_id):
        serializer = WorkerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        worker, _created = services.add_worker(membership=self.membership, **serializer.validated_data)
        return Response(WorkerSerializer(worker).data, status=status.HTTP_201_CREATED)


class WorkerImportView(WritesNeedPayments, APIView):
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def post(self, request, org_id):
        serializer = WorkerImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.import_workers(membership=self.membership, rows=serializer.validated_data["rows"])
        return Response(result)


class WorkerDetailView(WritesNeedPayments, APIView):
    def patch(self, request, org_id, worker_id):
        serializer = WorkerUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        worker = services.update_worker(membership=self.membership, worker_id=worker_id, **serializer.validated_data)
        return Response(WorkerSerializer(worker).data)

    def delete(self, request, org_id, worker_id):
        services.update_worker(membership=self.membership, worker_id=worker_id, is_active=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
