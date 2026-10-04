from django.contrib import admin
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display

from fluxpay.admin_base import ViewOnlyAdmin

from .models import AuditEvent


class AreaFilter(admin.SimpleListFilter):
    """Groups actions by their prefix: auth.*, transfer.*, org.*, payment.*, adjustment.*, config.* ..."""

    title = "area"
    parameter_name = "area"

    def lookups(self, request, model_admin):
        return (
            ("auth.", "Sign-ins & accounts"),
            ("transfer.", "Transfers"),
            ("adjustment.", "Staff top-ups & corrections"),
            ("org.", "Businesses"),
            ("payment.", "External payments"),
            ("statement.", "Statements"),
            ("config.", "Platform settings"),
        )

    def queryset(self, request, queryset):
        return queryset.filter(action__startswith=self.value()) if self.value() else queryset


@admin.register(AuditEvent)
class AuditEventAdmin(ViewOnlyAdmin):
    """Append-only and hash-chained: `manage.py verify_audit_log` detects any edit or deletion."""

    list_display = ("created_at", "action_label", "actor_label", "target_type", "target_id", "ip_address")
    list_filter = (AreaFilter, "action", ("created_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("actor_label", "action", "target_id", "ip_address")
    search_help_text = "Search by who did it (email), action, record id or IP address"
    date_hierarchy = "created_at"
    exclude = ("prev_hash",)

    @display(
        description="Action",
        label={"danger": "danger", "warning": "warning", "success": "success", "info": "info"},
    )
    def action_label(self, event):
        if event.action.endswith(("failed", "removed", "revoked", "debited", "rejected")):
            return "warning", event.action
        if event.action.startswith(("adjustment.", "config.")):
            return "danger", event.action  # staff power: stands out when scanning
        if event.action.startswith("auth."):
            return "info", event.action
        return "success", event.action
