from decimal import Decimal

from rest_framework import serializers

from .models import Account, Transaction, Transfer


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
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("1.00"))
    note = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(max_length=64, min_length=8)


class TransferSerializer(serializers.ModelSerializer):
    source_account_number = serializers.CharField(source="source.account_number")
    destination_account_number = serializers.CharField(source="destination.account_number")
    recipient_name = serializers.CharField(source="destination.owner.full_name")
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
