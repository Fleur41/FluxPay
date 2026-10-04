from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display
from unfold.widgets import UnfoldAdminSelectWidget

from fluxpay.admin_base import ViewOnlyAdmin, admin_link, money
from fluxpay.exceptions import BusinessError
from platform_settings import services as rules

from accounting import services as books
from accounting.models import CashbookEntry

from .models import Account, ManualAdjustment, Transaction, Transfer
from .services import post_adjustment


class WalletTypeFilter(admin.SimpleListFilter):
    title = "wallet type"
    parameter_name = "type"

    def lookups(self, request, model_admin):
        return (("personal", "Personal"), ("business", "Business"), ("system", "FluxPay system"))

    def queryset(self, request, queryset):
        return {
            "personal": queryset.filter(system_key__isnull=True, organization__isnull=True),
            "business": queryset.filter(organization__isnull=False),
            "system": queryset.filter(system_key__isnull=False),
        }.get(self.value(), queryset)


@admin.register(Account)
class AccountAdmin(ViewOnlyAdmin):
    list_display = ("account_number", "holder", "wallet_type", "balance_display", "status", "created_at")
    list_filter = (WalletTypeFilter, "currency", "is_active")
    search_fields = ("account_number", "owner__email", "owner__full_name", "organization__name")
    search_help_text = "Search by account number, owner email or name, or business name"
    list_select_related = ("owner", "organization")

    @display(description="Balance", ordering="balance")
    def balance_display(self, account):
        return money(account.balance, account.currency)

    def has_view_permission(self, request, obj=None):
        # Staff who post top-ups need to find wallets (the account search on the top-up form).
        return request.user.has_perm("banking.post_adjustment") or super().has_view_permission(request, obj)

    def get_search_results(self, request, queryset, search_term):
        # Autocomplete (e.g. on top-ups) offers customer and business wallets, never system accounts.
        queryset, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        if request.path.endswith("/autocomplete/"):
            queryset = queryset.filter(system_key__isnull=True)
        return queryset, may_have_duplicates

    @display(description="Holder", ordering="owner__full_name")
    def holder(self, account):
        if account.system_key:
            return account.name
        if account.organization_id:
            return admin_link(
                "admin:organizations_organization_change", account.organization_id, account.organization.name
            )
        return admin_link(
            "admin:users_user_change", account.owner_id, f"{account.owner.full_name} ({account.owner.email})"
        )

    @display(description="Type", label={"Personal": "info", "Business": "primary", "System": ""})
    def wallet_type(self, account):
        return "System" if account.system_key else "Business" if account.organization_id else "Personal"

    @display(description="Status", label={"Open": "success", "Closed": "danger"})
    def status(self, account):
        return "Open" if account.is_active else "Closed"


@admin.register(Transaction)
class TransactionAdmin(ViewOnlyAdmin):
    """The ledger: append-only."""

    list_display = (
        "created_at",
        "reference",
        "wallet",
        "direction",
        "category",
        "amount_display",
        "balance_after_display",
        "line_status",
    )
    list_filter = ("type", "category", "status", ("created_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("reference", "account__account_number", "counterparty_name", "description")
    search_help_text = "Search by reference, account number, counterparty or note"
    date_hierarchy = "created_at"
    list_select_related = ("account",)

    @display(description="Wallet", ordering="account__account_number")
    def wallet(self, line):
        return admin_link("admin:banking_account_change", line.account_id, line.account.account_number)

    @display(description="Direction", label={"CREDIT": "success", "DEBIT": "warning"})
    def direction(self, line):
        return line.type, "Money in" if line.type == Transaction.Type.CREDIT else "Money out"

    @display(description="Amount", ordering="amount")
    def amount_display(self, line):
        return money(line.amount, line.account.currency)

    @display(description="Balance after", ordering="balance_after")
    def balance_after_display(self, line):
        return money(line.balance_after, line.account.currency)

    @display(description="Status", label={"COMPLETED": "success", "PENDING": "info", "FAILED": "danger"})
    def line_status(self, line):
        return line.status, line.get_status_display()


@admin.register(Transfer)
class TransferAdmin(ViewOnlyAdmin):
    list_display = ("created_at", "reference", "from_wallet", "to_wallet", "amount_display", "note")
    list_filter = (("created_at", RangeDateFilter),)
    list_filter_submit = True
    search_fields = ("reference", "source__account_number", "destination__account_number", "note")
    date_hierarchy = "created_at"
    list_select_related = ("source", "destination")

    @display(description="Amount", ordering="amount")
    def amount_display(self, transfer):
        return money(transfer.amount, transfer.source.currency)

    @display(description="From")
    def from_wallet(self, transfer):
        return admin_link("admin:banking_account_change", transfer.source_id, transfer.source.account_number)

    @display(description="To")
    def to_wallet(self, transfer):
        return admin_link("admin:banking_account_change", transfer.destination_id, transfer.destination.account_number)


class ReceiptChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, entry):
        currency = entry.bank_account.currency
        return (
            f"{entry.number} · {entry.date:%d %b %Y} · {entry.counterparty} · "
            f"{currency} {entry.unallocated:,.2f} left of {entry.amount:,.2f}"
        )


class ManualAdjustmentForm(forms.ModelForm):
    cashbook_entry = ReceiptChoiceField(
        label="Bank receipt",
        queryset=CashbookEntry.objects.none(),
        widget=UnfoldAdminSelectWidget,
        help_text="The customer deposit in the cashbook this money comes from (or goes back to, for a correction).",
    )

    class Meta:
        model = ManualAdjustment
        fields = ("cashbook_entry", "account", "kind", "amount", "reason")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "cashbook_entry" not in self.fields:
            return  # the read-only view of a posted adjustment
        self.fields["cashbook_entry"].queryset = (
            CashbookEntry.objects.filter(category=CashbookEntry.Category.CUSTOMER_DEPOSIT, reversed_by__isnull=True)
            .select_related("bank_account")
            .order_by("-date", "-created_at")
        )
        self.fields["kind"].choices = [
            (ManualAdjustment.Kind.CREDIT, "Top-up: credit the wallet from the receipt"),
            (ManualAdjustment.Kind.DEBIT, "Correction: take money back from the wallet to the receipt"),
        ]

    def clean(self):
        """The service's checks, run here so a mistake shows as a form error rather than a server error."""
        data = super().clean()
        entry, account, kind, amount = (data.get(f) for f in ("cashbook_entry", "account", "kind", "amount"))
        if len((data.get("reason") or "").strip()) < 10:
            self.add_error("reason", "Give a reason of at least 10 characters for the audit trail.")
        if account is None or amount is None:
            return data
        if not account.is_active:
            self.add_error("account", "This wallet is closed.")
        try:
            rules.check_amount(amount, account.currency)
        except BusinessError as exc:
            self.add_error("amount", str(exc.detail))
        if kind == ManualAdjustment.Kind.DEBIT and amount > account.balance:
            self.add_error("amount", f"The wallet only holds {account.balance:,.2f} {account.currency}.")
        if entry is not None and kind:
            problem = books.allocation_problem(entry, kind=kind, amount=amount, wallet=account, staff=self.staff)
            if problem:
                self.add_error("cashbook_entry", problem)
        return data


@admin.register(ManualAdjustment)
class ManualAdjustmentAdmin(ModelAdmin):
    """Staff top-ups and corrections. Add-only: posted adjustments are never edited or deleted."""

    form = ManualAdjustmentForm
    autocomplete_fields = ("account",)
    radio_fields = {"kind": admin.HORIZONTAL}
    warn_unsaved_form = True
    list_display = (
        "created_at",
        "reference",
        "wallet",
        "kind_label",
        "amount_display",
        "balance_after_display",
        "receipt",
        "created_by",
    )
    list_filter = ("kind", ("created_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("reference", "account__account_number", "account__owner__email", "reason")
    search_help_text = "Search by reference, account number, customer email or reason"
    list_select_related = ("account", "created_by", "cashbook_entry")
    add_fieldsets = (
        (
            None,
            {
                "fields": ("cashbook_entry", "account", "kind", "amount", "reason"),
                "description": (
                    "Money only reaches a wallet from a customer deposit recorded in the cashbook (Accounting → "
                    "Cashbook). Pick the receipt, then find the wallet by account number, email or business name. "
                    "The customer is told by email and SMS; the reason stays internal and goes into the audit log."
                ),
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.add_fieldsets
        return (
            (
                None,
                {
                    "fields": (
                        "cashbook_entry",
                        "account",
                        "kind",
                        "amount",
                        "reason",
                        "reference",
                        "balance_after",
                        "created_by",
                        "created_at",
                    )
                },
            ),
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "account":
            kwargs["queryset"] = Account.objects.filter(system_key__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return (
            "cashbook_entry",
            "account",
            "kind",
            "amount",
            "reason",
            "reference",
            "balance_after",
            "created_by",
            "created_at",
        )

    def has_add_permission(self, request):
        return request.user.has_perm("banking.post_adjustment")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("banking.post_adjustment") or super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="Wallet", ordering="account__account_number")
    def wallet(self, adjustment):
        return admin_link("admin:banking_account_change", adjustment.account_id, adjustment.account.account_number)

    @display(description="Amount", ordering="amount")
    def amount_display(self, adjustment):
        return money(adjustment.amount, adjustment.account.currency)

    @display(description="Balance after", ordering="balance_after")
    def balance_after_display(self, adjustment):
        return money(adjustment.balance_after, adjustment.account.currency)

    @display(description="Kind", label={"CREDIT": "success", "DEBIT": "warning", "PAYOUT": "info"})
    def kind_label(self, adjustment):
        return adjustment.kind, {"CREDIT": "Top-up", "DEBIT": "Correction", "PAYOUT": "Cash withdrawal"}[
            adjustment.kind
        ]

    @display(description="Bank entry")
    def receipt(self, adjustment):
        if adjustment.cashbook_entry_id is None:
            return "Before cashbook"
        return admin_link(
            "admin:accounting_cashbookentry_change", adjustment.cashbook_entry_id, adjustment.cashbook_entry.number
        )

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        form.staff = request.user
        return form

    def save_model(self, request, obj, form, change):
        posted = post_adjustment(
            staff=request.user,
            account_id=obj.account_id,
            kind=obj.kind,
            amount=obj.amount,
            reason=obj.reason,
            cashbook_entry=form.cleaned_data["cashbook_entry"],
        )
        # The admin goes on to log and redirect using `obj`: point it at the posted row.
        obj.pk, obj.reference, obj.balance_after, obj.created_by = (
            posted.pk,
            posted.reference,
            posted.balance_after,
            posted.created_by,
        )
        obj._state.adding = False
