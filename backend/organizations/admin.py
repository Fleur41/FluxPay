from django.contrib import admin

from .models import Invitation, Membership, Organization, PaymentRequest


class MembershipInline(admin.TabularInline):
    model = Membership
    fk_name = "organization"
    extra = 0
    fields = ("user", "role", "is_active", "created_at")
    readonly_fields = fields
    can_delete = False


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "registration_number", "status", "approval_threshold", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "registration_number")
    inlines = (MembershipInline,)
    # Staff may suspend a business; everything else changes through the API so it is audited.
    readonly_fields = ("name", "registration_number", "approval_threshold", "created_by", "created_at", "updated_at")


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "organization", "role", "created_at", "expires_at", "accepted_at", "revoked_at")
    search_fields = ("email", "organization__name")
    exclude = ("token_hash",)

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ("organization", "amount", "destination_account_number", "status", "created_by", "created_at")
    list_filter = ("status",)
    search_fields = ("organization__name", "destination_account_number")

    def has_change_permission(self, request, obj=None):
        return False
