from django.contrib import admin
from django.db import transaction
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display

from audit.services import record
from fluxpay.admin_base import ViewOnlyAdmin

from .models import Beneficiary, Invitation, Membership, Organization, Payment


class MembershipInline(TabularInline):
    model = Membership
    fk_name = "organization"
    extra = 0
    fields = ("user", "role", "is_active", "created_at")
    readonly_fields = fields
    can_delete = False
    verbose_name_plural = "Members"

    def has_add_permission(self, request, obj=None):
        return False  # people join through invitations, so it is audited


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    """Staff may suspend or reactivate a business (audited); owners manage everything else in the app."""

    list_display = ("name", "registration_number", "status_label", "approval_threshold", "members", "workers",
                    "books", "created_at")  # fmt: skip
    list_filter = ("status", ("created_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("name", "registration_number")
    inlines = (MembershipInline,)
    fields = ("name", "registration_number", "status", "approval_threshold", "created_by", "created_at", "updated_at")
    readonly_fields = ("name", "registration_number", "approval_threshold", "created_by", "created_at", "updated_at")
    radio_fields = {"status": admin.HORIZONTAL}

    def has_add_permission(self, request):
        return False  # businesses are created by customers in the app

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="Status", label={"ACTIVE": "success", "SUSPENDED": "danger"})
    def status_label(self, organization):
        return organization.status, organization.get_status_display()

    @display(description="Members")
    def members(self, organization):
        return organization.memberships.filter(is_active=True).count()

    @display(description="Workers")
    def workers(self, organization):
        return organization.workers.filter(status="ACTIVE").count()

    @display(description="")
    def books(self, organization):
        from django.urls import reverse
        from django.utils.html import format_html

        return format_html(
            '<a class="text-primary-600" href="{}?organization={}">Books →</a>', reverse("accounting_business"),
            organization.pk,
        )  # fmt: skip

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if "status" in form.changed_data:
            record(
                "org.suspended" if obj.status == Organization.Status.SUSPENDED else "org.reactivated",
                actor=request.user,
                organization_id=obj.id,
                target=obj,
                metadata={"by_staff": True},
            )


@admin.register(Payment)
class PaymentAdmin(ViewOnlyAdmin):
    list_display = (
        "created_at",
        "organization",
        "type",
        "recipient_name",
        "amount",
        "status_label",
        "reference",
        "created_by",
        "decided_by",
    )
    list_filter = ("status", "type", ("created_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("reference", "organization__name", "recipient_name", "destination_account_number",
                     "created_by__email")  # fmt: skip
    list_select_related = ("organization", "created_by", "decided_by")

    @display(
        description="Status",
        label={
            "PENDING_APPROVAL": "warning",
            "PENDING": "info",
            "PROCESSING": "info",
            "COMPLETED": "success",
            "REJECTED": "danger",
            "CANCELLED": "",
            "FAILED": "danger",
            "REVERSED": "danger",
        },
    )
    def status_label(self, payment):
        return payment.status, payment.get_status_display()


@admin.register(Beneficiary)
class BeneficiaryAdmin(ViewOnlyAdmin):
    """Businesses manage their own beneficiaries in the app; staff can look them up here."""

    list_display = ("name", "organization", "kind", "method", "verified", "is_active", "details_changed_at")
    list_filter = ("kind", "method", "is_active")
    search_fields = ("name", "organization__name", "account_number", "mpesa_phone", "paybill_number",
                     "till_number", "bank_account_number")  # fmt: skip
    search_help_text = "Search by name, business, or any account, phone, paybill or till number"
    list_select_related = ("organization",)

    @display(description="Details", label={"Verified": "success", "Not verified": "warning"})
    def verified(self, beneficiary):
        return "Verified" if beneficiary.is_verified else "Not verified"


@admin.register(Invitation)
class InvitationAdmin(ViewOnlyAdmin):
    list_display = ("created_at", "email", "organization", "role", "state", "expires_at")
    list_filter = ("role",)
    search_fields = ("email", "organization__name")
    exclude = ("token_hash",)

    @display(description="State", label={"Accepted": "success", "Pending": "info", "Revoked": "", "Expired": ""})
    def state(self, invitation):
        from django.utils import timezone

        if invitation.accepted_at:
            return "Accepted"
        if invitation.revoked_at:
            return "Revoked"
        return "Expired" if invitation.expires_at <= timezone.now() else "Pending"
