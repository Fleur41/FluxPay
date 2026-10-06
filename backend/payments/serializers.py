import re
from decimal import Decimal

from rest_framework import serializers

from notifications.sms import normalize_phone

from .models import ExternalPayment


class ExternalPaymentSerializer(serializers.ModelSerializer):
    account_id = serializers.UUIDField(source="account.id", read_only=True)
    receipt = serializers.SerializerMethodField()  # the M-Pesa receipt or bank reference, once there is one

    def get_receipt(self, payment) -> str | None:
        return payment.metadata.get("provider_receipt") or payment.metadata.get("bank_reference") or None

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
            "receipt",
            "failure_reason",
            "created_at",
            "updated_at",
            "completed_at",
        )
        read_only_fields = fields



class MpesaPhoneField(serializers.CharField):
    """A Safaricom number in any local format (0712..., 712..., +254712...); returns 254712345678."""

    def to_internal_value(self, data):
        phone = normalize_phone(super().to_internal_value(data))
        if not phone or not re.fullmatch(r"\+254[17]\d{8}", phone):
            raise serializers.ValidationError("Enter a Safaricom number like 0712 345 678.")
        return phone.removeprefix("+")


class MpesaAmountSerializer(serializers.Serializer):
    phone_number = MpesaPhoneField(max_length=20)
    # Whole shillings and the platform's limits are checked by payments.services.check_payable_amount.
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("1.00"))
    idempotency_key = serializers.CharField(max_length=64, min_length=8)


class MpesaDepositSerializer(MpesaAmountSerializer):
    account_id = serializers.UUIDField()


class MpesaWithdrawalSerializer(MpesaDepositSerializer):
    phone_number = MpesaPhoneField(max_length=20, required=False)  # defaults to the user's own number
