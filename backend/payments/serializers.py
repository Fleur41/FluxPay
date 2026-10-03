import re
from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from .models import ExternalPayment


class ExternalPaymentSerializer(serializers.ModelSerializer):
    account_id = serializers.UUIDField(source="account.id", read_only=True)

    class Meta:
        model = ExternalPayment
        fields = (
            "id",
            "account_id",
            "direction",
            "rail",
            "method",
            "status",
            "amount",
            "currency",
            "fee",
            "reference",
            "failure_reason",
            "created_at",
            "updated_at",
            "completed_at",
        )
        read_only_fields = fields


class MpesaDepositSerializer(serializers.Serializer):
    account_id = serializers.UUIDField()
    phone_number = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("1.00"))
    idempotency_key = serializers.CharField(max_length=64, min_length=8)

    def validate_phone_number(self, value: str) -> str:
        """Accepts 0712345678, 712345678, +254712345678 or 254712345678; returns 254712345678."""
        digits = re.sub(r"[\s-]", "", value).removeprefix("+")
        if digits.startswith("0"):
            digits = "254" + digits[1:]
        elif len(digits) == 9:
            digits = "254" + digits
        if not re.fullmatch(r"254[17]\d{8}", digits):
            raise serializers.ValidationError("Enter a Safaricom number like 0712 345 678.")
        return digits

    def validate_amount(self, value: Decimal) -> Decimal:
        if value != value.to_integral_value():
            raise serializers.ValidationError("M-Pesa amounts must be whole shillings.")
        if value > settings.FLUXPAY_MAX_TRANSFER:
            raise serializers.ValidationError(f"Deposits are limited to {settings.FLUXPAY_MAX_TRANSFER:,.0f}.")
        return value
