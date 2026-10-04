from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "channel", "event", "reference", "status", "attempts")
    list_filter = ("channel", "status", "event")
    search_fields = ("reference", "user__email")
    readonly_fields = [f.name for f in Notification._meta.fields]

    def has_add_permission(self, request):
        return False
