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


# --- Staff looking at a business's data -------------------------------------------------------------

# Where each kind of record says which business it belongs to (the first that is set wins; a transfer can
# belong to two).
BUSINESS_PATHS = ("organization_id", "account.organization_id", "wallet.organization_id", "source.organization_id",
                  "destination.organization_id", "pay_run.organization_id")  # fmt: skip


def businesses_of(obj) -> set:
    from organizations.models import Organization

    if isinstance(obj, Organization):
        return {obj.pk}
    found = set()
    for path in BUSINESS_PATHS:
        value = obj
        for part in path.split("."):
            value = getattr(value, part, None)
            if value is None:
                break
        if value is not None:
            found.add(value)
    return found


def record_staff_view(request, *, organization_id, target=None, page: str) -> None:
    """Writes `staff.viewed_business_data` into the business's own audit log, so its owners can see who at
    FluxPay looked and when. At most once per staff member and record every 10 minutes."""
    from django.core.cache import cache

    from audit.services import record

    target_key = f"{type(target).__name__}:{target.pk}" if target is not None else f"list:{page}"
    if cache.add(f"staff-view:{request.user.pk}:{organization_id}:{target_key}", True, 600):
        record("staff.viewed_business_data", actor=request.user, organization_id=organization_id, target=target,
               metadata={"page": page, "path": request.get_full_path()[:200]})  # fmt: skip


class StaffViewAuditMixin:
    """For admins showing a business's records: opening one (or a list filtered to one business) is audited."""

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if request.method == "GET":
            obj = self.get_object(request, object_id)
            if obj is not None:
                for organization_id in businesses_of(obj):
                    record_staff_view(request, organization_id=organization_id, target=obj,
                                      page=str(self.model._meta.verbose_name))  # fmt: skip
        return super().change_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        import uuid

        for key, value in request.GET.items():
            if "organization" in key and key.endswith(("__exact", "organization")):
                try:
                    organization_id = uuid.UUID(value)
                except ValueError:
                    continue
                record_staff_view(request, organization_id=organization_id,
                                  page=str(self.model._meta.verbose_name_plural))  # fmt: skip
        return super().changelist_view(request, extra_context)
