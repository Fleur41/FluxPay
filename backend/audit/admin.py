from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "action", "actor_label", "organization_id", "target_type", "ip_address")
    list_filter = ("action",)
    search_fields = ("actor_label", "action", "target_id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False  # the audit log is append-only

    def has_delete_permission(self, request, obj=None):
        return False
