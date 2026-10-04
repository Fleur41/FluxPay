from django.contrib import admin
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display

from fluxpay.admin_base import ViewOnlyAdmin, admin_link

from .models import ExternalPayment, WebhookEvent

STATUS_COLOURS = {
    "CREATED": "",
    "PENDING": "info",
    "HELD": "info",
    "SUBMITTED": "info",
    "COMPLETED": "success",
    "FAILED": "danger",
    "EXPIRED": "",
    "REVERSED": "warning",
}


@admin.register(ExternalPayment)
class ExternalPaymentAdmin(ViewOnlyAdmin):
    """Deposits and payouts through outside providers. Status only changes through payments.services."""

    list_display = ("created_at", "reference", "wallet", "kind", "rail", "amount", "currency", "status_label", "review")
    list_filter = ("needs_review", "status", "direction", "rail", ("created_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("reference", "provider_ref", "account__account_number", "account__owner__email")
    search_help_text = "Search by reference, provider reference, account number or customer email"
    list_select_related = ("account",)
    exclude = ("metadata",)  # may hold phone numbers; shown only where needed

    @display(description="Wallet")
    def wallet(self, payment):
        return admin_link("admin:banking_account_change", payment.account_id, payment.account.account_number)

    @display(description="Kind", label={"IN": "success", "OUT": "warning"})
    def kind(self, payment):
        return payment.direction, payment.get_direction_display()

    @display(description="Status", label=STATUS_COLOURS)
    def status_label(self, payment):
        return payment.status, payment.get_status_display()

    @display(description="Review", label={"Needs review": "danger"})
    def review(self, payment):
        return "Needs review" if payment.needs_review else ""


@admin.register(WebhookEvent)
class WebhookEventAdmin(ViewOnlyAdmin):
    list_display = ("received_at", "rail", "event_id", "payment", "outcome")
    list_filter = ("rail", ("received_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("event_id",)

    @display(description="Outcome", label={"Processed": "success", "Error": "danger", "Waiting": "info"})
    def outcome(self, event):
        if event.error:
            return "Error"
        return "Processed" if event.processed_at else "Waiting"
