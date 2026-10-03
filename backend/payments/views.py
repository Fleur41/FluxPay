from django.conf import settings
from django.http import Http404
from django.utils.crypto import constant_time_compare
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from fluxpay.exceptions import BusinessError

from .models import ExternalPayment, Rail
from .providers.base import InvalidCallback
from .serializers import ExternalPaymentSerializer, MpesaDepositSerializer
from .services import record_webhook, start_deposit

# Never stored with a callback.
DROPPED_HEADERS = {"authorization", "cookie"}


class PaymentListView(generics.ListAPIView):
    serializer_class = ExternalPaymentSerializer
    filterset_fields = ("rail", "direction", "status")
    ordering = ("-created_at",)

    def get_queryset(self):
        return ExternalPayment.objects.select_related("account").filter(account__owner=self.request.user)


class PaymentDetailView(generics.RetrieveAPIView):
    serializer_class = ExternalPaymentSerializer

    def get_queryset(self):
        return ExternalPayment.objects.select_related("account").filter(account__owner=self.request.user)


class MpesaDepositView(APIView):
    """POST /deposits/mpesa/ — sends an STK Push; the wallet is credited once M-Pesa confirms.

    Answers 202 with the PENDING payment; the app polls GET /payments/<id>/ until it settles.
    """

    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "deposits"

    def post(self, request):
        serializer = MpesaDepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment, created = start_deposit(
            user=request.user,
            account_id=data["account_id"],
            rail=Rail.MPESA,
            method=ExternalPayment.Method.STK,
            amount=data["amount"],
            idempotency_key=data["idempotency_key"],
            metadata={"phone_number": data["phone_number"]},
        )
        payment.refresh_from_db()  # the submit may already have run (inline mode)
        return Response(
            {"payment": ExternalPaymentSerializer(payment).data},
            status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK,
        )


class WebhookView(APIView):
    """POST /hooks/<rail>/<token>/ — provider callbacks. Stores the event, queues it, answers fast."""

    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = ()  # providers send bursts; the token and the event inbox are the protection

    def post(self, request, rail: str, token: str):
        expected = settings.FLUXPAY_WEBHOOK_TOKEN
        rail = rail.upper()
        if not expected or not constant_time_compare(token, expected):
            raise Http404
        if rail not in settings.FLUXPAY_PAYMENT_PROVIDERS:
            raise Http404
        if not isinstance(request.data, dict):
            raise BusinessError("Callback body must be a JSON object.", "invalid_callback")

        headers = {k: v for k, v in request.headers.items() if k.lower() not in DROPPED_HEADERS}
        try:
            event = record_webhook(rail, headers, dict(request.data))
        except InvalidCallback as exc:
            raise BusinessError(str(exc), "invalid_callback") from exc
        return Response({"received": True, "duplicate": event is None}, status=status.HTTP_200_OK)
