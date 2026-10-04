from django.contrib import admin
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display

from fluxpay.admin_base import ViewOnlyAdmin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(ViewOnlyAdmin):
    """Every transaction alert sent (or not) by email and SMS."""

    list_display = ("created_at", "user", "channel_label", "event", "reference", "status_label", "attempts")
    list_filter = ("status", "channel", "event", ("created_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("reference", "user__email", "destination")
    search_help_text = "Search by reference, customer email, or the email address / phone it went to"
    list_select_related = ("user",)

    @display(description="Channel", label={"EMAIL": "info", "SMS": "primary"})
    def channel_label(self, notification):
        return notification.channel, notification.get_channel_display()

    @display(description="Status", label={"SENT": "success", "QUEUED": "info", "FAILED": "danger"})
    def status_label(self, notification):
        return notification.status, notification.get_status_display()
