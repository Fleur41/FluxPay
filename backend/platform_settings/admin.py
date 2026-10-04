from django.contrib import admin
from django.db import transaction
from unfold.admin import ModelAdmin
from unfold.decorators import display

from audit.services import record

from .models import Currency, PlatformSettings


def changes_in(form) -> dict:
    return {
        field: {"from": str(form.initial.get(field, "")), "to": str(form.cleaned_data.get(field, ""))}
        for field in form.changed_data
    }


@admin.register(Currency)
class CurrencyAdmin(ModelAdmin):
    list_display = ("code", "name", "status", "min_transfer", "max_transfer", "signup_bonus", "sort_order")
    list_filter = ("enabled",)
    warn_unsaved_form = True
    fieldsets = (
        ("Currency", {"fields": ("code", "name", "enabled", "sort_order")}),
        ("Limits per transfer, payment or withdrawal", {"fields": ("min_transfer", "max_transfer")}),
        (
            "Promotion",
            {
                "fields": ("signup_bonus",),
                "description": (
                    "Paid to each new personal wallet in this currency. Keep at 0 unless running a promotion."
                ),
            },
        ),
    )

    @display(description="Status", label={"Enabled": "success", "Disabled": ""})
    def status(self, currency):
        return "Enabled" if currency.enabled else "Disabled"

    def get_readonly_fields(self, request, obj=None):
        return ("code",) if obj else ()  # wallets reference the code

    def has_delete_permission(self, request, obj=None):
        return False  # disable a currency instead; wallets may still use it

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if form.changed_data:
            record("config.currency_changed", actor=request.user, target=obj, metadata={"changes": changes_in(form)})


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(ModelAdmin):
    list_display = ("__str__", "default_currency", "session_timeout_minutes", "updated_at", "updated_by")
    readonly_fields = ("updated_at", "updated_by")
    warn_unsaved_form = True
    fieldsets = (
        ("Wallets", {"fields": ("default_currency",)}),
        ("Statements & invitations", {"fields": ("statement_max_days", "invitation_expiry_days")}),
        ("Payroll", {"fields": ("payroll_reversal_days",)}),
        ("App security", {"fields": ("session_timeout_minutes",)}),
        (
            "Budget planner guideline",
            {
                "fields": ("budget_needs_percent", "budget_wants_percent", "budget_savings_percent"),
                "description": "The split the app's budget planner compares plans with. Must add up to 100.",
            },
        ),
        ("Last change", {"fields": ("updated_at", "updated_by")}),
    )

    def changelist_view(self, request, extra_context=None):
        # There is exactly one row: go straight to it.
        from django.shortcuts import redirect

        return redirect("admin:platform_settings_platformsettings_change", 1)

    def has_add_permission(self, request):
        return False  # exactly one row, created by migration

    def has_delete_permission(self, request, obj=None):
        return False

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        if form.changed_data:
            record("config.settings_changed", actor=request.user, target=obj, metadata={"changes": changes_in(form)})
