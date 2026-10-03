from django.contrib import admin

from .models import ExternalPayment, WebhookEvent


@admin.register(ExternalPayment)
class ExternalPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "reference", "direction", "rail", "status", "amount", "currency", "account", "needs_review", "created_at"
    )
    list_filter = ("rail", "direction", "status", "needs_review")
    search_fields = ("reference", "provider_ref", "account__account_number", "account__owner__email")

    def has_change_permission(self, request, obj=None):
        return False  # status only changes through payments.services


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("rail", "event_id", "payment", "received_at", "processed_at", "error")
    list_filter = ("rail",)
    search_fields = ("event_id",)

    def has_change_permission(self, request, obj=None):
        return False
