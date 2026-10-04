from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from platform_settings import services as rules

from .models import Account, Transaction, Transfer
from .services import holder_name


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ("id", "account_number", "name", "currency", "balance", "is_active", "created_at", "updated_at")
        read_only_fields = fields


class AccountLookupSerializer(serializers.ModelSerializer):
    """What a sender may see about a recipient before confirming a transfer."""

    holder_name = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ("account_number", "currency", "holder_name")

    def get_holder_name(self, obj) -> str:
        if obj.organization_id:
            return obj.organization.name  # businesses are shown by their full name
        parts = obj.owner.full_name.split()
        if len(parts) < 2:
            return obj.owner.full_name
        return f"{parts[0]} {parts[-1][0]}."


class TransactionSerializer(serializers.ModelSerializer):
    account_id = serializers.UUIDField(source="account.id", read_only=True)
    currency = serializers.CharField(source="account.currency", read_only=True)

    class Meta:
        model = Transaction
        fields = (
            "id",
            "account_id",
            "type",
            "category",
            "status",
            "amount",
            "currency",
            "balance_after",
            "counterparty_name",
            "counterparty_account",
            "description",
            "reference",
            "created_at",
        )
        read_only_fields = fields


class TransferCreateSerializer(serializers.Serializer):
    source_account_id = serializers.UUIDField()
    destination_account_number = serializers.RegexField(r"^\d{10}$", error_messages={"invalid": "Account numbers are 10 digits."})
    # Positive only; the currency's minimum and maximum are enforced by the service (platform_settings).
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(max_length=64, min_length=8)


class TransferSerializer(serializers.ModelSerializer):
    source_account_number = serializers.CharField(source="source.account_number")
    destination_account_number = serializers.CharField(source="destination.account_number")
    recipient_name = serializers.SerializerMethodField()
    currency = serializers.CharField(source="source.currency")

    class Meta:
        model = Transfer
        fields = (
            "id",
            "reference",
            "amount",
            "currency",
            "note",
            "source_account_number",
            "destination_account_number",
            "recipient_name",
            "created_at",
        )

    def get_recipient_name(self, obj) -> str:
        return holder_name(obj.destination)


class StatementRequestSerializer(serializers.Serializer):
    """Query parameters for a statement download. `file_format`, because DRF reserves `format`."""

    account_id = serializers.UUIDField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    file_format = serializers.ChoiceField(choices=("pdf", "csv"), default="pdf")

    def validate(self, attrs):
        today = timezone.localdate(timezone=ZoneInfo(settings.FLUXPAY_DISPLAY_TIMEZONE))
        attrs["date_to"] = attrs.get("date_to") or today
        attrs["date_from"] = attrs.get("date_from") or attrs["date_to"] - timedelta(days=29)
        if attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError("date_from must be on or before date_to.")
        max_days = rules.platform().statement_max_days
        if (attrs["date_to"] - attrs["date_from"]).days >= max_days:
            raise serializers.ValidationError(f"A statement can cover at most {max_days} days.")
        return attrs
