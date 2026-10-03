from django.conf import settings
from django.http import Http404
from django.utils.crypto import constant_time_compare
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from fluxpay.exceptions import BusinessError

from .models import ExternalPayment
from .providers.base import InvalidCallback
from .serializers import ExternalPaymentSerializer
from .services import record_webhook

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
