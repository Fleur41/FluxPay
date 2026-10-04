from decimal import Decimal

from rest_framework import serializers

from audit.models import AuditEvent

from .models import Invitation, Membership, Organization, PaymentRequest

ROLE_CHOICES = Membership.Role.choices


class OrganizationSerializer(serializers.ModelSerializer):
    my_role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ("id", "name", "registration_number", "status", "approval_threshold", "my_role", "created_at")
        read_only_fields = fields

    def get_my_role(self, obj) -> str | None:
        roles = self.context.get("roles", {})
        return roles.get(obj.id)


class OrganizationCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    registration_number = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    currency = serializers.CharField(max_length=3, required=False)  # checked against enabled currencies


class OrganizationUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    registration_number = serializers.CharField(max_length=50, required=False, allow_blank=True)
    approval_threshold = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False
    )


class MemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "email", "full_name", "role", "created_at")
        read_only_fields = fields


class RoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ROLE_CHOICES)


class InvitationSerializer(serializers.ModelSerializer):
    invited_by = serializers.EmailField(source="invited_by.email", read_only=True)

    class Meta:
        model = Invitation
        fields = ("id", "email", "role", "invited_by", "created_at", "expires_at")
        read_only_fields = fields


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=ROLE_CHOICES)


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128)


class PaymentRequestSerializer(serializers.ModelSerializer):
    source_account_number = serializers.CharField(source="source_account.account_number", read_only=True)
    currency = serializers.CharField(source="source_account.currency", read_only=True)
    created_by = serializers.EmailField(source="created_by.email", read_only=True)
    decided_by = serializers.EmailField(source="decided_by.email", read_only=True, default=None)
    reference = serializers.CharField(source="transfer.reference", read_only=True, default=None)

    class Meta:
        model = PaymentRequest
        fields = (
            "id",
            "status",
            "amount",
            "currency",
            "source_account_number",
            "destination_account_number",
            "note",
            "books_category",
            "created_by",
            "decided_by",
            "decided_at",
            "decision_note",
            "failure_reason",
            "reference",
            "created_at",
        )
        read_only_fields = fields


class PaymentRequestCreateSerializer(serializers.Serializer):
    source_account_id = serializers.UUIDField()
    destination_account_number = serializers.RegexField(
        r"^\d{10}$", error_messages={"invalid": "Account numbers are 10 digits."}
    )
    # Positive only; the currency's minimum and maximum are enforced by the service (platform_settings).
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    # Files the payment in the business's books; defaults to purchases and suppliers.
    books_category = serializers.ChoiceField(
        choices=["suppliers", "expenses", "salaries", "drawings"], required=False, default="suppliers"
    )
    idempotency_key = serializers.CharField(max_length=64, min_length=8)


class DecisionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ("id", "created_at", "actor_label", "action", "target_type", "target_id", "metadata", "ip_address")
        read_only_fields = fields

