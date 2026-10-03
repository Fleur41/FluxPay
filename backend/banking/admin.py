from django.contrib import admin

from .models import Account, Transaction, Transfer


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("account_number", "owner", "name", "currency", "balance", "is_active", "created_at")
    list_filter = ("currency", "is_active")
    search_fields = ("account_number", "owner__email", "owner__full_name")
    readonly_fields = ("balance",)  # balances only change through banking.services


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("reference", "account", "type", "category", "amount", "balance_after", "status", "created_at")
    list_filter = ("type", "category", "status")
    search_fields = ("reference", "account__account_number", "counterparty_name")

    def has_change_permission(self, request, obj=None):
        return False  # the ledger is append-only


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = ("reference", "source", "destination", "amount", "created_at")
    search_fields = ("reference",)

    def has_change_permission(self, request, obj=None):
        return False
