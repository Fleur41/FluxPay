from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display
from unfold.widgets import (
    UnfoldAdminDateWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextInputWidget,
)

from accounting.models import BankAccount
from fluxpay.admin_base import StaffViewAuditMixin, ViewOnlyAdmin, admin_link
from fluxpay.exceptions import BusinessError

from . import services
from .models import ExternalPayment, WebhookEvent

UNSETTLED = (ExternalPayment.Status.HELD, ExternalPayment.Status.SUBMITTED)
# Payout details staff may need to send or check a payout; never secrets.
PAYOUT_FIELDS = {
    "recipient": "Recipient", "mpesa_phone": "M-Pesa number", "paybill_number": "Paybill",
    "paybill_account": "Paybill account", "till_number": "Till", "bank_name": "Bank", "bank_branch": "Branch",
    "bank_account_name": "Account name", "bank_account_number": "Account number", "bank_swift_code": "SWIFT",
    "provider_receipt": "Receipt", "bank_reference": "Bank reference", "cashbook_entry": "Cashbook entry",
    "staff_note": "Staff note", "confirmed_by": "Settled by",
}  # fmt: skip


class StaffQueueFilter(admin.SimpleListFilter):
    title = "staff queue"
    parameter_name = "queue"

    def lookups(self, request, model_admin):
        return (("bank", "Bank payouts to send"), ("review", "Needs review"))

    def queryset(self, request, queryset):
        if self.value() == "bank":
            return queryset.filter(rail="BANK", direction="OUT", status__in=UNSETTLED)
        if self.value() == "review":
            return queryset.filter(needs_review=True)
        return queryset


class SettlePayoutForm(forms.Form):
    outcome = forms.ChoiceField(
        choices=(("sent", "It was paid"), ("failed", "It was not paid: return the money")),
        widget=UnfoldAdminSelectWidget,
    )
    bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.filter(is_active=True), required=False, widget=UnfoldAdminSelectWidget,
        help_text="The FluxPay bank account the transfer was sent from.",
    )  # fmt: skip
    date = forms.DateField(required=False, widget=UnfoldAdminDateWidget, help_text="The date on the bank statement.")
    receipt = forms.CharField(
        max_length=60, required=False, widget=UnfoldAdminTextInputWidget,
        help_text="The bank's transaction reference, or the M-Pesa receipt (e.g. NLJ7RT61SV).",
    )  # fmt: skip
    note = forms.CharField(
        max_length=255, required=False, widget=UnfoldAdminTextInputWidget,
        help_text='How you checked, or why it failed, e.g. "Bank returned it: account closed".',
    )  # fmt: skip

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
class ExternalPaymentAdmin(StaffViewAuditMixin, ViewOnlyAdmin):
    """Deposits and payouts through outside providers. Status only changes through payments.services."""

    list_display = ("created_at", "reference", "wallet", "kind", "rail", "amount", "currency", "status_label", "review")
    list_filter = (StaffQueueFilter, "needs_review", "status", "direction", "rail", ("created_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("reference", "provider_ref", "account__account_number", "account__owner__email")
    search_help_text = "Search by reference, provider reference, account number or customer email"
    list_select_related = ("account",)
    exclude = ("metadata",)  # may hold phone numbers; shown only where needed
    readonly_fields = ("payout_details", "settle_link")

    def get_fields(self, request, obj=None):
        fields = [f for f in super().get_fields(request, obj) if f not in self.readonly_fields]
        return ["settle_link", "payout_details", *fields]

    @display(description="Payout details")
    def payout_details(self, payment):
        rows = [(label, payment.metadata[key]) for key, label in PAYOUT_FIELDS.items() if payment.metadata.get(key)]
        return format_html_join("", "<div><strong>{}:</strong> {}</div>", rows) if rows else "-"

    @display(description="Staff action")
    def settle_link(self, payment):
        if payment.direction != "OUT" or payment.status not in UNSETTLED:
            return "-"
        url = reverse("admin:payments_externalpayment_settle", args=[payment.pk])
        text = "Confirm or fail this bank payout" if payment.rail == "BANK" else "Confirm or fail this payout by hand"
        return format_html('<a class="text-primary-600 font-semibold" href="{}">{}</a>', url, text)

    def get_urls(self):
        return [
            path(
                "<uuid:object_id>/settle/",
                self.admin_site.admin_view(self.settle_view),
                name="payments_externalpayment_settle",
            ),
        ] + super().get_urls()

    def settle_view(self, request, object_id):
        """Bank payouts: staff sent the transfer (or it bounced). Other rails: a payout with no result that staff
        checked with the provider. Paid bank payouts are also recorded in FluxPay's cashbook."""
        payment = get_object_or_404(ExternalPayment, pk=object_id)
        bank = payment.rail == "BANK"
        if not request.user.has_perm("payments.settle_payout") or (
            bank and not request.user.has_perm("accounting.record_cashbook")
        ):
            raise PermissionDenied
        back = reverse("admin:payments_externalpayment_change", args=[payment.pk])
        form = SettlePayoutForm(request.POST or None, initial={"date": timezone.localdate()})
        form.fields["bank_account"].queryset = BankAccount.objects.filter(is_active=True, currency=payment.currency)
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            try:
                if data["outcome"] == "failed":
                    services.staff_fail_payout(staff=request.user, payment_id=payment.pk, reason=data["note"])
                elif bank:
                    if data["bank_account"] is None or data["date"] is None:
                        raise BusinessError("Choose the bank account and the date it was sent.", "bank_required")
                    services.confirm_bank_payout(
                        staff=request.user, payment_id=payment.pk, bank=data["bank_account"],
                        bank_reference=data["receipt"], date=data["date"],
                    )  # fmt: skip
                else:
                    services.staff_complete_payout(
                        staff=request.user, payment_id=payment.pk, receipt=data["receipt"], note=data["note"]
                    )
            except BusinessError as exc:
                messages.error(request, str(exc.detail))
            else:
                payment.refresh_from_db()
                messages.success(request, f"{payment.reference} is now {payment.get_status_display().lower()}.")
                return HttpResponseRedirect(back)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Settle payout {payment.reference}",
            "payment": payment,
            "bank": bank,
            "details": [(label, payment.metadata[key]) for key, label in PAYOUT_FIELDS.items() if payment.metadata.get(key)],
            "form": form,
            "back": back,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "payments/settle.html", context)

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
