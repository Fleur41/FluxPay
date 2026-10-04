from decimal import Decimal

from rest_framework import serializers

from audit.models import AuditEvent

from . import beneficiaries
from .models import Beneficiary, Invitation, Membership, Organization, Payment

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
            "beneficiary_id",
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


BOOKS_CATEGORIES = ["suppliers", "contractors", "expenses", "salaries", "allowances", "bonuses", "commissions",
                    "drawings"]  # fmt: skip


class PaymentCreateSerializer(serializers.Serializer):
    # Optional when paying a beneficiary: it then follows the beneficiary's kind.
    type = serializers.ChoiceField(choices=Payment.Type.choices, required=False, allow_blank=True, default="")
    # For the worker types (salary, allowance, bonus, commission, other worker payment).
    worker_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    # For a saved beneficiary (a supplier, the landlord...).
    beneficiary_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    # For anyone else: the recipient's FluxPay account.
    destination_account_number = serializers.RegexField(
        r"^\d{10}$", required=False, allow_blank=True, default="",
        error_messages={"invalid": "Account numbers are 10 digits."},
    )  # fmt: skip
    # Positive only; the currency's minimum and maximum are enforced by the service (platform_settings).
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")
    # Files the payment in the business's books; by default it follows the type (salaries, suppliers...).
    books_category = serializers.ChoiceField(choices=BOOKS_CATEGORIES, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(max_length=64, min_length=8)

    def validate(self, data):
        if data["type"] in Payment.WORKER_TYPES:
            if not data["worker_id"]:
                raise serializers.ValidationError({"worker_id": "Choose the worker to pay."})
        elif data["beneficiary_id"] and data["destination_account_number"]:
            raise serializers.ValidationError("Pay either a beneficiary or an account number, not both.")
        elif not data["beneficiary_id"]:
            if not data["type"]:
                raise serializers.ValidationError({"type": "Choose what the payment is for."})
            if not data["destination_account_number"]:
                raise serializers.ValidationError(
                    {"destination_account_number": "Give the recipient's account number, or choose a beneficiary."}
                )
        return data


class BeneficiarySerializer(serializers.ModelSerializer):
    """Payout details are masked for members who can't manage beneficiaries (context `full_details`)."""

    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    details = serializers.SerializerMethodField()
    is_verified = serializers.BooleanField(read_only=True)
    verified_by = serializers.CharField(source="verified_by.full_name", read_only=True, default=None)
    details_changed_by = serializers.CharField(source="details_changed_by.full_name", read_only=True)

    class Meta:
        model = Beneficiary
        fields = ("id", "name", "kind", "kind_label", "books_category", "contact_phone", "contact_email", "notes",
                  "method", "method_label", "details", "is_verified", "verified_by", "verified_at",
                  "details_changed_by", "details_changed_at", "is_active", "created_at")  # fmt: skip
        read_only_fields = fields

    def get_details(self, beneficiary) -> dict:
        details = {k: v for k, v in beneficiary.payout_details().items() if k != "method"}
        return details if self.context.get("full_details") else beneficiaries.mask(details)


class BeneficiaryWriteSerializer(serializers.Serializer):
    """Create (name, kind, method and that method's details required) or change (any subset)."""

    name = serializers.CharField(max_length=150)
    kind = serializers.ChoiceField(choices=Beneficiary.Kind.choices)
    books_category = serializers.ChoiceField(choices=BOOKS_CATEGORIES, required=False, allow_blank=True)
    contact_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    method = serializers.ChoiceField(choices=Beneficiary.Method.choices)
    # Which of these are needed depends on `method`; organizations.beneficiaries checks them.
    account_number = serializers.CharField(max_length=10, required=False, allow_blank=True)
    mpesa_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    paybill_number = serializers.CharField(max_length=7, required=False, allow_blank=True)
    paybill_account = serializers.CharField(max_length=20, required=False, allow_blank=True)
    till_number = serializers.CharField(max_length=7, required=False, allow_blank=True)
    bank_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    bank_branch = serializers.CharField(max_length=80, required=False, allow_blank=True)
    bank_account_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    bank_account_number = serializers.CharField(max_length=40, required=False, allow_blank=True)
    bank_swift_code = serializers.CharField(max_length=11, required=False, allow_blank=True)


class DecisionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ReverseSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=200)


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ("id", "created_at", "actor_label", "action", "target_type", "target_id", "metadata", "ip_address")
        read_only_fields = fields

