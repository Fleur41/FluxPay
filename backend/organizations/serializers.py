from decimal import Decimal

from rest_framework import serializers

from audit.models import AuditEvent

from .models import Invitation, Membership, Organization, Payment

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


class PaymentSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    source_account_number = serializers.CharField(source="source_account.account_number", read_only=True)
    currency = serializers.CharField(source="source_account.currency", read_only=True)
    created_by = serializers.EmailField(source="created_by.email", read_only=True)
    decided_by = serializers.EmailField(source="decided_by.email", read_only=True, default=None)
    reversal_reference = serializers.CharField(source="reversal.reference", read_only=True, default=None)

    class Meta:
        model = Payment
        fields = (
            "id",
            "reference",
            "type",
            "type_label",
            "status",
            "status_label",
            "amount",
            "currency",
            "source_account_number",
            "recipient_name",
            "destination_account_number",
            "worker_id",
            "pay_run_id",
            "note",
            "books_category",
            "created_by",
            "decided_by",
            "decided_at",
            "decision_note",
            "failure_reason",
            "created_at",
            "completed_at",
            "reversed_at",
            "reversal_reason",
            "reversal_reference",
        )
        read_only_fields = fields


class PaymentCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=Payment.Type.choices)
    # For the worker types (salary, allowance, bonus, commission, other worker payment).
    worker_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    # For everyone else: the recipient's FluxPay account.
    destination_account_number = serializers.RegexField(
        r"^\d{10}$", required=False, allow_blank=True, default="",
        error_messages={"invalid": "Account numbers are 10 digits."},
    )  # fmt: skip
    # Positive only; the currency's minimum and maximum are enforced by the service (platform_settings).
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    # Files the payment in the business's books; by default it follows the type (salaries, suppliers...).
    books_category = serializers.ChoiceField(
        choices=["suppliers", "contractors", "expenses", "salaries", "allowances", "bonuses", "commissions",
                 "drawings"],
        required=False, allow_blank=True, default="",
    )  # fmt: skip
    idempotency_key = serializers.CharField(max_length=64, min_length=8)

    def validate(self, data):
        if data["type"] in Payment.WORKER_TYPES:
            if not data["worker_id"]:
                raise serializers.ValidationError({"worker_id": "Choose the worker to pay."})
        elif not data["destination_account_number"]:
            raise serializers.ValidationError({"destination_account_number": "Give the recipient's account number."})
        return data


class DecisionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ReverseSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=200)


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ("id", "created_at", "actor_label", "action", "target_type", "target_id", "metadata", "ip_address")
        read_only_fields = fields

