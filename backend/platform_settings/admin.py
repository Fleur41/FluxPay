from django.contrib import admin
from django.db import transaction

from audit.services import record

from .models import Currency, PlatformSettings


def changes_in(form) -> dict:
    return {
        field: {"from": str(form.initial.get(field, "")), "to": str(form.cleaned_data.get(field, ""))}
        for field in form.changed_data
    }


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "enabled", "min_transfer", "max_transfer", "signup_bonus", "sort_order")
    list_filter = ("enabled",)

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
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "default_currency", "session_timeout_minutes", "updated_at", "updated_by")
    readonly_fields = ("updated_at", "updated_by")

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
