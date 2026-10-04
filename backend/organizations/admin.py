from django.contrib import admin
from django.db import transaction
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display

from audit.services import record
from fluxpay.admin_base import ViewOnlyAdmin

from .models import Invitation, Membership, Organization, PaymentRequest


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

    list_display = ("name", "registration_number", "status_label", "approval_threshold", "members", "created_at")
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


@admin.register(PaymentRequest)
class PaymentRequestAdmin(ViewOnlyAdmin):
    list_display = (
        "created_at",
        "organization",
        "amount",
        "destination_account_number",
        "status_label",
        "created_by",
        "decided_by",
    )
    list_filter = ("status", ("created_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("organization__name", "destination_account_number", "created_by__email")
    list_select_related = ("organization", "created_by", "decided_by")

    @display(
        description="Status",
        label={
            "PENDING_APPROVAL": "warning",
            "EXECUTED": "success",
            "REJECTED": "danger",
            "CANCELLED": "",
            "FAILED": "danger",
        },
    )
    def status_label(self, request_):
        return request_.status, request_.get_status_display()


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
