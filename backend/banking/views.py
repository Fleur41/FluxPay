from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from fluxpay.exceptions import BusinessError

from .filters import TransactionFilter
from .models import Account, Transaction
from .serializers import (
    AccountLookupSerializer,
    AccountSerializer,
    TransactionSerializer,
    TransferCreateSerializer,
    TransferSerializer,
)
from .services import transfer_funds


class AccountListView(generics.ListAPIView):
    serializer_class = AccountSerializer
    pagination_class = None

    def get_queryset(self):
        return Account.objects.filter(owner=self.request.user, is_active=True)


class AccountLookupView(APIView):
    """GET /accounts/lookup/?account_number=1234567890 — confirm who you're paying."""

    def get(self, request):
        number = request.query_params.get("account_number", "")
        account = Account.objects.select_related("owner").filter(account_number=number, is_active=True).first()
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
        return Transaction.objects.select_related("account").filter(account__owner=self.request.user)


class TransactionDetailView(generics.RetrieveAPIView):
    serializer_class = TransactionSerializer

    def get_queryset(self):
        return Transaction.objects.select_related("account").filter(account__owner=self.request.user)


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
