from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.db.models import F, Sum
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display
from unfold.widgets import (
    UnfoldAdminSelectWidget,
    UnfoldAdminTextInputWidget,
)

from audit.services import record
from banking.models import Account, ManualAdjustment
from fluxpay.admin_base import admin_link, money
from fluxpay.exceptions import BusinessError
from platform_settings.services import enabled_currencies

from . import services
from .models import (
    AccountingSettings,
    BankAccount,
    BusinessEntry,
    BankReconciliation,
    CashbookEntry,
    JournalEntry,
    JournalLine,
    LedgerAccount,
)

Category = CashbookEntry.Category

CATEGORY_CHOICES = [
    ("", "Choose what the money was for"),
    (
        "Money in",
        [
            (Category.CUSTOMER_DEPOSIT, "Customer deposit: cash or a transfer from a customer, to credit their wallet"),
            (Category.CAPITAL, "Owner's capital: the owners putting money into FluxPay"),
            (Category.INTEREST, "Interest paid by the bank"),
            (Category.OTHER_INCOME, "Other income"),
        ],
    ),
    (
        "Money out",
        [
            (Category.CUSTOMER_PAYOUT, "Customer withdrawal: cash or a transfer paid out of a customer's wallet"),
            (Category.BANK_CHARGES, "Bank charges"),
            (Category.EXPENSE, "Business expense (rent, salaries, ...)"),
            (Category.DRAWINGS, "Owner's drawings: the owners taking money out"),
            (Category.BANK_TRANSFER, "Transfer to another FluxPay bank account"),
        ],
    ),
]


def _currency_choices():
    return [(c.code, f"{c.code} ({c.name})") for c in enabled_currencies()]


def _button(href, text, icon, variant="primary"):
    styles = {
        "primary": "bg-primary-600 text-white border-transparent",
        "default": "border-base-200 bg-white text-important dark:border-base-700 dark:bg-transparent",
    }
    return format_html(
        '<a href="{}" class="font-medium inline-flex items-center gap-1 rounded-default px-3 py-2 border {}">'
        '<span class="material-symbols-outlined">{}</span> {}</a>',
        href,
        styles[variant],
        icon,
        text,
    )


def _report(name, **params):
    from urllib.parse import urlencode

    return reverse(f"accounting_{name}") + ("?" + urlencode(params) if params else "")


# --- Chart of accounts ---------------------------------------------------------------------------


class BooksFilter(admin.SimpleListFilter):
    """FluxPay's own books by default; a business's books on request."""

    title = "books"
    parameter_name = "books"

    def lookups(self, request, model_admin):
        return (("fluxpay", "FluxPay's own books"), ("business", "Businesses' books"))

    def choices(self, changelist):
        for lookup, title in self.lookup_choices:
            yield {
                "selected": (self.value() or "fluxpay") == lookup,
                "query_string": changelist.get_query_string({self.parameter_name: lookup}),
                "display": title,
            }

    def queryset(self, request, queryset):
        if self.value() == "business":
            return queryset.filter(organization__isnull=False)
        return queryset.filter(organization__isnull=True)


class LedgerAccountForm(forms.ModelForm):
    currency = forms.ChoiceField(widget=UnfoldAdminSelectWidget)

    class Meta:
        model = LedgerAccount
        fields = ("code", "name", "type", "currency", "description", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "currency" in self.fields:
            self.fields["currency"].choices = _currency_choices()
        if "code" in self.fields:
            self.fields[
                "code"
            ].help_text = (
                "Assets 1000s, liabilities 2000s, equity 3000s, income 4000s, expenses 5000s, e.g. 5910 for rent."
            )

    def clean(self):
        data = super().clean()
        code, kind = data.get("code") or "", data.get("type")
        expected = {"ASSET": "1", "LIABILITY": "2", "EQUITY": "3", "INCOME": "4", "EXPENSE": "5"}.get(kind)
        if expected and not code.startswith(expected):
            self.add_error("code", f"{LedgerAccount.Type(kind).label} accounts use codes starting with {expected}.")
        return data


@admin.register(LedgerAccount)
class LedgerAccountAdmin(ModelAdmin):
    form = LedgerAccountForm
    list_display = ("code", "name", "type_label", "currency", "books_of", "balance", "kind", "open_ledger")
    list_filter = (BooksFilter, "currency", "type", "is_active")
    list_select_related = ("organization",)
    search_fields = ("code", "name")
    search_help_text = "Search by code or name"
    ordering = ("currency", "code")
    list_per_page = 100

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        locked = ("code", "type", "currency")
        return locked + (("name", "is_active") if obj.role else ())

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(dr=Sum("lines__debit"), cr=Sum("lines__credit"))

    @display(description="Books")
    def books_of(self, account):
        return account.organization.name if account.organization_id else "FluxPay"

    @display(
        description="Type",
        label={"ASSET": "info", "LIABILITY": "warning", "EQUITY": "primary", "INCOME": "success", "EXPENSE": "danger"},
    )
    def type_label(self, account):
        return account.type, account.get_type_display()

    @display(description="Balance")
    def balance(self, account):
        dr, cr = account.dr or 0, account.cr or 0
        return money(dr - cr if account.debit_normal else cr - dr, account.currency)

    @display(description="", label={"Control": "", "System": "", "Custom": "info"})
    def kind(self, account):
        return "Control" if account.is_control else "System" if account.role else "Custom"

    @display(description="")
    def open_ledger(self, account):
        return format_html('<a class="text-primary-600" href="{}">Ledger →</a>', _report("ledger", account=account.pk))


# --- Bank accounts -------------------------------------------------------------------------------


class BankAccountForm(forms.ModelForm):
    currency = forms.ChoiceField(widget=UnfoldAdminSelectWidget)

    class Meta:
        model = BankAccount
        fields = ("name", "bank_name", "account_number", "branch", "currency", "purpose", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "currency" in self.fields:
            self.fields["currency"].choices = _currency_choices()


@admin.register(BankAccount)
class BankAccountAdmin(ModelAdmin):
    form = BankAccountForm
    list_display = ("name", "bank_name", "account_number", "purpose_label", "balance", "links", "is_active")
    list_filter = ("currency", "purpose", "is_active")
    search_fields = ("name", "bank_name", "account_number")
    radio_fields = {"purpose": admin.VERTICAL}

    def get_readonly_fields(self, request, obj=None):
        return ("currency", "purpose", "ledger_code") if obj else ()

    def get_fields(self, request, obj=None):
        fields = ["name", "bank_name", "account_number", "branch", "currency", "purpose", "is_active"]
        return fields + ["ledger_code"] if obj else fields

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="Ledger account")
    def ledger_code(self, bank):
        return str(bank.ledger_account)

    @display(description="Holds", label={"SAFEGUARDING": "success", "OPERATING": "info"})
    def purpose_label(self, bank):
        return bank.purpose, "Customer funds" if bank.purpose == BankAccount.Purpose.SAFEGUARDING else "Own money"

    @display(description="Cashbook balance")
    def balance(self, bank):
        return money(services.bank_balance(bank), bank.currency)

    @display(description="")
    def links(self, bank):
        return format_html(
            '<a class="text-primary-600" href="{}">Cashbook</a> · <a class="text-primary-600" href="{}">Reconcile</a>',
            _report("cashbook", bank=bank.pk),
            _report("reconcile", bank=bank.pk),
        )

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        fields = {name: form.cleaned_data[name] for name in form.Meta.fields}
        bank = services.open_bank_account(**fields)
        record(
            "bank_account.opened",
            actor=request.user,
            target=bank,
            metadata={"name": bank.name, "currency": bank.currency},
        )
        obj.pk, obj.ledger_account = bank.pk, bank.ledger_account
        obj._state.adding = False


# --- Cashbook ------------------------------------------------------------------------------------


class CashbookEntryForm(forms.ModelForm):
    category = forms.ChoiceField(choices=CATEGORY_CHOICES, widget=UnfoldAdminSelectWidget)
    wallet_number = forms.CharField(
        label="Customer's wallet number",
        required=False,
        max_length=10,
        widget=UnfoldAdminTextInputWidget,
        help_text="Customer withdrawals only: the 10-digit account number to pay out of.",
    )
    transfer_to = forms.ModelChoiceField(
        queryset=BankAccount.objects.filter(is_active=True),
        required=False,
        widget=UnfoldAdminSelectWidget,
        help_text="Transfers between FluxPay bank accounts only.",
    )

    class Meta:
        model = CashbookEntry
        fields = (
            "bank_account",
            "category",
            "date",
            "amount",
            "counterparty",
            "bank_reference",
            "description",
            "ledger_account",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "bank_account" not in self.fields:
            return  # the read-only view of a posted entry
        self.fields["bank_account"].queryset = BankAccount.objects.filter(is_active=True)
        self.fields["date"].initial = services.business_date()
        accounts = self.fields["ledger_account"]
        accounts.queryset = LedgerAccount.objects.filter(
            type__in=[LedgerAccount.Type.INCOME, LedgerAccount.Type.EXPENSE],
            is_control=False,
            is_active=True,
            organization__isnull=True,
        )
        accounts.label = "Income or expense account"
        accounts.help_text = (
            "Other income and business expenses only. Leave empty for 4900 Other income / 5900 Operating expenses."
        )

    def clean(self):
        data = super().clean()
        self.wallet = None
        number = (data.get("wallet_number") or "").strip()
        if data.get("category") == Category.CUSTOMER_PAYOUT and number:
            self.wallet = Account.objects.filter(account_number=number, system_key__isnull=True).first()
            if self.wallet is None:
                self.add_error("wallet_number", "No wallet with that number.")
                return data
        if self.wallet is None and data.get("category") == Category.CUSTOMER_PAYOUT:
            self.add_error("wallet_number", "Enter the wallet number the customer is withdrawing from.")
            return data
        problems = services.cashbook_problems(
            bank=data.get("bank_account"),
            category=data.get("category"),
            amount=data.get("amount"),
            date=data.get("date"),
            ledger_account=data.get("ledger_account"),
            wallet=self.wallet,
            transfer_to=data.get("transfer_to"),
        )
        for name, message in problems.items():
            self.add_error("wallet_number" if name == "wallet" else name, message)
        return data


class AllocationInline(TabularInline):
    model = ManualAdjustment
    fk_name = "cashbook_entry"
    extra = 0
    can_delete = False
    fields = ("created_at", "wallet", "kind", "amount", "created_by")
    readonly_fields = fields
    verbose_name = "wallet movement"
    verbose_name_plural = "Wallets credited from this entry"

    def has_add_permission(self, request, obj=None):
        return False

    @display(description="Wallet")
    def wallet(self, adjustment):
        return admin_link("admin:banking_account_change", adjustment.account_id, adjustment.account.account_number)


class AllocationStatusFilter(admin.SimpleListFilter):
    title = "allocation"
    parameter_name = "allocation"

    def lookups(self, request, model_admin):
        return (("open", "Not fully credited to wallets"), ("done", "Fully credited"))

    def queryset(self, request, queryset):
        deposits = queryset.filter(category=Category.CUSTOMER_DEPOSIT, reversed_by__isnull=True)
        if self.value() == "open":
            return deposits.filter(allocated__lt=F("amount"))
        if self.value() == "done":
            return deposits.filter(allocated=F("amount"))
        return queryset


class ClearedFilter(admin.SimpleListFilter):
    title = "on bank statement"
    parameter_name = "cleared"

    def lookups(self, request, model_admin):
        return (("yes", "Matched to a statement"), ("no", "Not yet matched"))

    def queryset(self, request, queryset):
        return {"yes": queryset.filter(cleared_on__isnull=False), "no": queryset.filter(cleared_on__isnull=True)}.get(
            self.value(), queryset
        )


class ReverseForm(forms.Form):
    reason = forms.CharField(
        min_length=10,
        max_length=200,
        widget=UnfoldAdminTextInputWidget,
        help_text='Why it was wrong, e.g. "Recorded twice: same deposit slip as RCT-000012".',
    )


@admin.register(CashbookEntry)
class CashbookEntryAdmin(ModelAdmin):
    form = CashbookEntryForm
    warn_unsaved_form = True
    list_display = (
        "number_display",
        "date_display",
        "bank_account",
        "direction_label",
        "category",
        "counterparty",
        "amount_display",
        "status_label",
        "cleared",
    )
    list_filter = (
        "bank_account",
        "direction",
        "category",
        AllocationStatusFilter,
        ClearedFilter,
        ("date", RangeDateFilter),
    )
    list_filter_submit = True
    search_fields = ("number", "counterparty", "bank_reference", "description")
    search_help_text = "Search by number, who paid or was paid, bank reference or description"
    list_select_related = ("bank_account", "reversed_by")
    date_hierarchy = "date"
    inlines = (AllocationInline,)
    add_fieldsets = (
        (
            "Where and when",
            {
                "fields": ("bank_account", "category", "date"),
                "description": "Record money exactly as it appears on the bank statement. Customer deposits wait "
                "here as unallocated receipts until staff credit them to the customer's wallet.",
            },
        ),
        ("Amount and who", {"fields": ("amount", "counterparty", "bank_reference", "description")}),
        ("Only for some kinds of entry", {"fields": ("wallet_number", "transfer_to", "ledger_account")}),
    )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.add_fieldsets
        return (
            (None, {"fields": ("next_steps",)}),
            (
                "Entry",
                {
                    "fields": (
                        "number",
                        "bank_account",
                        "direction",
                        "category",
                        "date",
                        "amount_display",
                        "counterparty",
                        "bank_reference",
                        "description",
                        "ledger_account",
                    )
                },
            ),
            ("Customer deposit", {"fields": ("allocated_display", "unallocated_display")}),
            ("Books", {"fields": ("journal_link", "related", "cleared_on", "created_by", "created_at")}),
        )

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return (
            "next_steps", "number", "bank_account", "direction", "category", "date", "amount_display", "counterparty",
            "bank_reference", "description", "ledger_account", "allocated_display", "unallocated_display",
            "journal_link", "related", "cleared_on", "created_by", "created_at",
        )  # fmt: skip

    def get_inlines(self, request, obj):
        return self.inlines if obj and obj.adjustments.exists() else ()

    def has_add_permission(self, request):
        return request.user.has_perm("accounting.record_cashbook")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("accounting.record_cashbook") or super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # Columns

    @display(description="Number", ordering="number")
    def number_display(self, entry):
        return format_html('<span style="white-space: nowrap">{}</span>', entry.number)

    @display(description="Date", ordering="date")
    def date_display(self, entry):
        return format_html('<span style="white-space: nowrap">{}</span>', entry.date.strftime("%d %b %Y"))

    @display(description="Direction", label={"RECEIPT": "success", "PAYMENT": "warning"})
    def direction_label(self, entry):
        return entry.direction, entry.get_direction_display()

    @display(description="Amount", ordering="amount")
    def amount_display(self, entry):
        return format_html('<span style="white-space: nowrap">{}</span>', money(entry.amount, entry.bank_account.currency))

    @display(
        description="Status",
        label={
            "Reversed": "",
            "To credit": "warning",
            "Part credited": "warning",
            "Credited": "success",
            "Posted": "info",
        },
    )
    def status_label(self, entry):
        if entry.is_reversed:
            return "Reversed"
        if entry.category != Category.CUSTOMER_DEPOSIT:
            return "Posted"
        if entry.allocated == 0:
            return "To credit"
        return "Credited" if entry.allocated == entry.amount else "Part credited"

    @display(description="On statement", boolean=True)
    def cleared(self, entry):
        return entry.cleared_on is not None

    # Detail fields

    @display(description="Credited to wallets")
    def allocated_display(self, entry):
        return (
            money(entry.allocated, entry.bank_account.currency) if entry.category == Category.CUSTOMER_DEPOSIT else "-"
        )

    @display(description="Still to credit")
    def unallocated_display(self, entry):
        if entry.category != Category.CUSTOMER_DEPOSIT:
            return "-"
        return money(entry.unallocated, entry.bank_account.currency)

    @display(description="Journal")
    def journal_link(self, entry):
        if entry.journal_id is None:
            return "-"
        return admin_link("admin:accounting_journalentry_change", entry.journal_id, entry.journal.number)

    @display(description="Related entries")
    def related(self, entry):
        links = []
        for label, other in (
            ("Other half of the transfer", entry.counterpart),
            ("Reverses", entry.reverses),
            ("Reversed by", getattr(entry, "reversed_by", None)),
        ):
            if other is not None:
                links.append((label, reverse("admin:accounting_cashbookentry_change", args=[other.pk]), other.number))
        if not links:
            return "-"
        return format_html_join(format_html("<br>"), '{}: <a class="text-primary-600" href="{}">{}</a>', links)

    @display(description="")
    def next_steps(self, entry):
        buttons = []
        user = self._request.user if hasattr(self, "_request") else None
        if (
            entry.category == Category.CUSTOMER_DEPOSIT
            and not entry.is_reversed
            and entry.unallocated > 0
            and user is not None
            and user.has_perm("banking.post_adjustment")
        ):
            url = reverse("admin:banking_manualadjustment_add") + f"?cashbook_entry={entry.pk}&kind=CREDIT"
            buttons.append(
                _button(
                    url, f"Credit a wallet ({money(entry.unallocated, entry.bank_account.currency)} left)", "add_card"
                )
            )
        if (
            services.reversal_problem(entry) is None
            and user is not None
            and user.has_perm("accounting.record_cashbook")
        ):
            url = reverse("admin:accounting_cashbookentry_reverse", args=[entry.pk])
            buttons.append(_button(url, "Reverse this entry", "undo", "default"))
        if not buttons:
            return "Nothing to do: this entry is fully posted."
        return format_html(
            '<div class="flex flex-wrap gap-2">{}</div>', format_html_join("", "{}", ((b,) for b in buttons))
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        self._request = request
        return super().change_view(request, object_id, form_url, extra_context)

    # Saving and reversing

    def save_model(self, request, obj, form, change):
        data = form.cleaned_data
        entry = services.record_cashbook_entry(
            staff=request.user,
            bank=data["bank_account"],
            category=data["category"],
            amount=data["amount"],
            date=data["date"],
            counterparty=data["counterparty"],
            description=data["description"],
            bank_reference=data.get("bank_reference") or "",
            ledger_account=data.get("ledger_account"),
            wallet=form.wallet,
            transfer_to=data.get("transfer_to"),
        )
        obj.pk, obj.number, obj.direction = entry.pk, entry.number, entry.direction
        obj._state.adding = False

    def response_add(self, request, obj, post_url_continue=None):
        entry = CashbookEntry.objects.get(pk=obj.pk)
        if entry.category == Category.CUSTOMER_DEPOSIT and request.user.has_perm("banking.post_adjustment"):
            messages.info(request, f"{entry.number} is waiting to be credited to the customer's wallet.")
            return HttpResponseRedirect(reverse("admin:accounting_cashbookentry_change", args=[entry.pk]))
        return super().response_add(request, obj, post_url_continue)

    def get_urls(self):
        return [
            path(
                "<uuid:object_id>/reverse/",
                self.admin_site.admin_view(self.reverse_view),
                name="accounting_cashbookentry_reverse",
            ),
        ] + super().get_urls()

    def reverse_view(self, request, object_id):
        entry = get_object_or_404(CashbookEntry, pk=object_id)
        if not request.user.has_perm("accounting.record_cashbook"):
            raise PermissionDenied
        back = reverse("admin:accounting_cashbookentry_change", args=[entry.pk])
        problem = services.reversal_problem(entry)
        if problem:
            messages.error(request, problem)
            return HttpResponseRedirect(back)
        form = ReverseForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                reversal = services.reverse_cashbook_entry(
                    staff=request.user, entry=entry, reason=form.cleaned_data["reason"]
                )
            except BusinessError as exc:
                messages.error(request, str(exc.detail))
                return HttpResponseRedirect(back)
            messages.success(request, f"{entry.number} was reversed by {reversal.number}.")
            return HttpResponseRedirect(reverse("admin:accounting_cashbookentry_change", args=[reversal.pk]))
        context = {
            **self.admin_site.each_context(request),
            "title": f"Reverse {entry.number}",
            "entry": entry,
            "form": form,
            "back": back,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "accounting/reverse.html", context)


# --- Journals ------------------------------------------------------------------------------------


class JournalLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        lines = [f.cleaned_data for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        if len(lines) < 2:
            raise forms.ValidationError("A journal needs at least two lines.")
        debit = sum((line.get("debit") or 0) for line in lines)
        credit = sum((line.get("credit") or 0) for line in lines)
        for line in lines:
            if bool(line.get("debit")) == bool(line.get("credit")):
                raise forms.ValidationError("Each line needs either a debit or a credit, not both.")
        if debit != credit:
            raise forms.ValidationError(f"Debits ({debit:,.2f}) and credits ({credit:,.2f}) must be equal.")
        if len({line["account"].currency for line in lines}) > 1:
            raise forms.ValidationError("All lines must be in the same currency.")


class JournalLineInline(TabularInline):
    model = JournalLine
    formset = JournalLineFormSet
    fields = ("account", "description", "debit", "credit")
    extra = 2
    min_num = 0
    can_delete = False
    verbose_name_plural = "Lines"

    def get_extra(self, request, obj=None, **kwargs):
        return 0 if obj else 2

    def get_readonly_fields(self, request, obj=None):
        return self.fields if obj else ()

    def has_add_permission(self, request, obj=None):
        return obj is None

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "account":
            kwargs["queryset"] = LedgerAccount.objects.filter(is_control=False, is_active=True, organization__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ("date", "memo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "date" in self.fields:
            self.fields["date"].initial = services.business_date()

    def clean_date(self):
        when = self.cleaned_data["date"]
        if problem := services.date_problem(when):
            raise forms.ValidationError(problem)
        return when


@admin.register(JournalEntry)
class JournalEntryAdmin(ModelAdmin):
    form = JournalEntryForm
    inlines = (JournalLineInline,)
    list_display = ("number", "date", "memo", "source_label", "total", "reference", "created_by")
    list_filter = (BooksFilter, "source", "currency", ("date", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("number", "memo", "reference")
    search_help_text = "Search by journal number, memo or reference (wallet, receipt or payment number)"
    date_hierarchy = "date"
    list_select_related = ("created_by",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(amount=Sum("lines__debit"))

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("date", "memo")
        return ("number", "date", "currency", "memo", "source", "reference", "reversal", "created_by", "created_at")

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj else ()

    def has_add_permission(self, request):
        return request.user.has_perm("accounting.post_journal")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(
        description="Source",
        label={
            "CASHBOOK": "info",
            "ALLOCATION": "success",
            "WALLET": "primary",
            "MANUAL": "warning",
            "OPENING": "",
            "REVERSAL": "danger",
        },
    )
    def source_label(self, entry):
        return entry.source, entry.get_source_display()

    @display(description="Amount", ordering="amount")
    def total(self, entry):
        return money(entry.amount, entry.currency)

    @display(description="Reversal")
    def reversal(self, entry):
        if entry.reverses_id:
            return format_html(
                "Reverses {}",
                admin_link("admin:accounting_journalentry_change", entry.reverses_id, entry.reverses.number),
            )
        other = getattr(entry, "reversed_by", None)
        if other:
            return format_html(
                "Reversed by {}", admin_link("admin:accounting_journalentry_change", other.pk, other.number)
            )
        if entry.source == JournalEntry.Source.MANUAL and self._can_post(entry):
            return _button(
                reverse("admin:accounting_journalentry_reverse", args=[entry.pk]),
                "Reverse this journal",
                "undo",
                "default",
            )
        return "-"

    def _can_post(self, entry):
        return getattr(self, "_request", None) is not None and self._request.user.has_perm("accounting.post_journal")

    def change_view(self, request, object_id, form_url="", extra_context=None):
        self._request = request
        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        pass  # posted with its lines in save_related, through the service

    def save_related(self, request, form, formsets, change):
        lines = [
            (
                f.cleaned_data["account"],
                f.cleaned_data.get("debit") or 0,
                f.cleaned_data.get("credit") or 0,
                f.cleaned_data.get("description") or "",
            )
            for formset in formsets
            for f in formset.forms
            if f.cleaned_data and not f.cleaned_data.get("DELETE")
        ]
        entry = services.post_manual_journal(
            staff=request.user, date=form.cleaned_data["date"], memo=form.cleaned_data["memo"], lines=lines
        )
        form.instance.pk, form.instance.number = entry.pk, entry.number
        form.instance._state.adding = False

    def get_urls(self):
        return [
            path(
                "<uuid:object_id>/reverse/",
                self.admin_site.admin_view(self.reverse_view),
                name="accounting_journalentry_reverse",
            ),
        ] + super().get_urls()

    def reverse_view(self, request, object_id):
        entry = get_object_or_404(JournalEntry, pk=object_id)
        back = reverse("admin:accounting_journalentry_change", args=[entry.pk])
        if not request.user.has_perm("accounting.post_journal"):
            raise PermissionDenied
        form = ReverseForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                reversal = services.reverse_manual_journal(
                    staff=request.user, entry=entry, reason=form.cleaned_data["reason"]
                )
            except BusinessError as exc:
                messages.error(request, str(exc.detail))
                return HttpResponseRedirect(back)
            messages.success(request, f"{entry.number} was reversed by {reversal.number}.")
            return HttpResponseRedirect(reverse("admin:accounting_journalentry_change", args=[reversal.pk]))
        context = {
            **self.admin_site.each_context(request),
            "title": f"Reverse {entry.number}",
            "entry": entry,
            "form": form,
            "back": back,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "accounting/reverse.html", context)


# --- Businesses' books ---------------------------------------------------------------------------


@admin.register(BusinessEntry)
class BusinessEntryAdmin(ModelAdmin):
    """Every business's cashbook lines, read-only. Businesses re-file categories themselves in the app."""

    list_display = ("date", "business", "wallet_number", "direction_label", "amount_display", "category_name",
                    "counterparty", "description", "source")  # fmt: skip
    list_filter = ("organization", "direction", "source", ("date", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("organization__name", "counterparty", "description", "reference")
    search_help_text = "Search by business, counterparty, description or reference"
    list_select_related = ("organization", "wallet", "category")
    date_hierarchy = "date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="Business", ordering="organization__name")
    def business(self, entry):
        return format_html(
            '<a class="text-primary-600" href="{}">{}</a>', _report("business", organization=entry.organization_id),
            entry.organization.name,
        )  # fmt: skip

    @display(description="Wallet")
    def wallet_number(self, entry):
        return entry.wallet.account_number

    @display(description="Direction", label={"IN": "success", "OUT": "warning"})
    def direction_label(self, entry):
        return entry.direction, entry.get_direction_display()

    @display(description="Amount", ordering="amount")
    def amount_display(self, entry):
        return format_html('<span style="white-space: nowrap">{}</span>', money(entry.amount, entry.wallet.currency))

    @display(description="Category", ordering="category__name")
    def category_name(self, entry):
        return entry.category.name


# --- Reconciliations and settings ----------------------------------------------------------------


@admin.register(BankReconciliation)
class BankReconciliationAdmin(ModelAdmin):
    list_display = (
        "statement_date",
        "bank_account",
        "statement_balance_display",
        "cashbook_display",
        "entries_cleared",
        "prepared_by",
        "created_at",
    )
    list_filter = ("bank_account",)
    list_select_related = ("bank_account", "prepared_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="Per bank statement")
    def statement_balance_display(self, rec):
        return money(rec.statement_balance, rec.bank_account.currency)

    @display(description="Per cashbook")
    def cashbook_display(self, rec):
        return money(rec.cashbook_balance, rec.bank_account.currency)

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "title": "Bank reconciliations"}
        if request.user.has_perm("accounting.reconcile_bank"):
            messages.info(
                request,
                format_html(
                    'Start a new one from <a class="underline" href="{}">Reconcile a bank account</a>.',
                    _report("reconcile"),
                ),
            )
        return super().changelist_view(request, extra_context)


@admin.register(AccountingSettings)
class AccountingSettingsAdmin(ModelAdmin):
    fields = ("books_closed_until", "require_second_person", "updated_at", "updated_by")
    readonly_fields = ("updated_at", "updated_by")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        services.books()
        return HttpResponseRedirect(reverse("admin:accounting_accountingsettings_change", args=[1]))

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        record(
            "accounting.settings_changed",
            actor=request.user,
            target=obj,
            metadata={name: str(form.cleaned_data[name]) for name in form.changed_data},
        )
