"""Shared building blocks for the back-office screens."""

from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin


def admin_link(url_name: str, pk, text: str) -> str:
    """A link to another back-office record, styled like the rest of the admin."""
    return format_html(
        '<a class="text-primary-600 dark:text-primary-500" href="{}">{}</a>', reverse(url_name, args=[pk]), text
    )


class ViewOnlyAdmin(ModelAdmin):
    """Records the services write (ledger, payments, alerts, audit): staff can look, never add, edit or delete."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def money(amount, currency: str = "") -> str:
    """12345.5 -> "KES 12,345.50": thousands separators make large amounts readable at a glance."""
    if amount is None:
        return "-"
    return f"{currency} {amount:,.2f}".strip()
