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

