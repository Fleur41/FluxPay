from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from audit.services import record
from fluxpay.exceptions import BusinessError

from .filters import TransactionFilter
from .models import Account, Transaction
from .serializers import (
    AccountLookupSerializer,
    AccountSerializer,
    StatementRequestSerializer,
    TransactionSerializer,
    TransferCreateSerializer,
    TransferSerializer,
)
from .services import transfer_funds
from .statements import build_statement, render_csv, render_pdf


class AccountListView(generics.ListAPIView):
    serializer_class = AccountSerializer
    pagination_class = None

    def get_queryset(self):
        return Account.objects.filter(owner=self.request.user, organization__isnull=True, is_active=True)


class AccountLookupView(APIView):
    """GET /accounts/lookup/?account_number=1234567890 — confirm who you're paying."""

    def get(self, request):
        number = request.query_params.get("account_number", "")
        account = (
            Account.objects.select_related("owner", "organization")
            .filter(account_number=number, is_active=True, system_key__isnull=True)
            .first()
        )
        if account is None:
            raise BusinessError("No active account with that number.", "recipient_not_found", status.HTTP_404_NOT_FOUND)
        return Response(AccountLookupSerializer(account).data)


class TransactionListView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    filterset_class = TransactionFilter
    search_fields = ("description", "counterparty_name", "counterparty_account", "reference")
    ordering_fields = ("created_at", "amount")
    ordering = ("-created_at",)

    def get_queryset(self):
        return Transaction.objects.select_related("account").filter(
            account__owner=self.request.user, account__organization__isnull=True
        )


class TransactionDetailView(generics.RetrieveAPIView):
    serializer_class = TransactionSerializer

    def get_queryset(self):
        return Transaction.objects.select_related("account").filter(
            account__owner=self.request.user, account__organization__isnull=True
        )


class TransferCreateView(APIView):
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "transfers"

    def post(self, request):
        serializer = TransferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        transfer, debit, created = transfer_funds(
            user=request.user,
            source_id=data["source_account_id"],
            destination_number=data["destination_account_number"],
            amount=data["amount"],
            note=data["note"],
            idempotency_key=data["idempotency_key"],
        )
        return Response(
            {"transfer": TransferSerializer(transfer).data, "transaction": TransactionSerializer(debit).data},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


def statement_response(request, accounts, *, organization_id=None):
    """Validates the query, builds the statement for one of `accounts` and returns it as a download."""
    params = StatementRequestSerializer(data=request.query_params)
    params.is_valid(raise_exception=True)
    data = params.validated_data
    account = accounts.filter(id=data["account_id"]).first() if "account_id" in data else accounts.first()
    if account is None:
        raise BusinessError("Account not found.", "account_not_found", status.HTTP_404_NOT_FOUND)

    statement = build_statement(account, data["date_from"], data["date_to"])
    file_format = data["file_format"]
    content = render_pdf(statement) if file_format == "pdf" else render_csv(statement)
    record(
        "statement.downloaded",
        actor=request.user,
        organization_id=organization_id,
        target=account,
        metadata={"from": str(statement.start), "to": str(statement.end), "format": file_format},
    )
    response = HttpResponse(content, content_type="application/pdf" if file_format == "pdf" else "text/csv")
    response["Content-Disposition"] = f'attachment; filename="{statement.filename_stem}.{file_format}"'
    return response


class StatementView(APIView):
    """GET /statements/?account_id=&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&file_format=pdf|csv"""

    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "statements"

    def get(self, request):
        accounts = Account.objects.select_related("owner").filter(
            owner=request.user, organization__isnull=True, is_active=True
        )
        return statement_response(request, accounts)
