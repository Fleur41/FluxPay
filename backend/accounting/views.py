"""Financial report pages inside the staff back-office. Every report can also be downloaded as CSV."""

import csv
from datetime import date as Date
from decimal import Decimal, InvalidOperation

from django.contrib import admin, messages
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.dateparse import parse_date

from fluxpay.exceptions import BusinessError
from platform_settings.services import platform

from . import reports
from .models import BankAccount, CashbookEntry, LedgerAccount
from .services import bank_balance, business_date, reconcile_bank

REPORTS = permission_required("accounting.view_financial_reports", raise_exception=True)
RECONCILE = permission_required("accounting.reconcile_bank", raise_exception=True)


def _date(request, name: str, default: Date) -> Date:
    return parse_date(request.GET.get(name) or "") or default


def _currency(request) -> str:
    available = reports.currencies()
    chosen = request.GET.get("currency")
    if chosen in available:
        return chosen
    default = platform().default_currency_id
    return default if default in available or not available else available[0]


def _page(request, template: str, title: str, **context) -> TemplateResponse:
    return TemplateResponse(
        request,
        template,
        {
            **admin.site.each_context(request),
            "title": title,
            "currencies": reports.currencies(),
            "csv_url": request.get_full_path() + ("&" if request.GET else "?") + "export=csv",
            **context,
        },
    )


def _csv(filename: str, header: list, rows: list) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


def _period(request):
    today = business_date()
    return _date(request, "start", today.replace(day=1)), _date(request, "end", today)


@REPORTS
def index(request):
    safeguarding = [reports.safeguarding(c) for c in reports.currencies()]
    return _page(request, "accounting/index.html", "Financial reports", safeguarding=safeguarding)


@REPORTS
def trial_balance(request):
    currency, as_at = _currency(request), _date(request, "as_at", business_date())
    data = reports.trial_balance(currency, as_at)
    if request.GET.get("export") == "csv":
        rows = [[r["account"].code, r["account"].name, r["debit"] or "", r["credit"] or ""] for r in data["rows"]]
        rows.append(["", "Total", data["total_debit"], data["total_credit"]])
        return _csv(f"trial-balance-{currency}-{as_at}.csv", ["Code", "Account", "Debit", "Credit"], rows)
    return _page(request, "accounting/trial_balance.html", "Trial balance", currency=currency, as_at=as_at, tb=data)


@REPORTS
def balance_sheet(request):
    currency, as_at = _currency(request), _date(request, "as_at", business_date())
    data = reports.balance_sheet(currency, as_at)
    if request.GET.get("export") == "csv":
        rows = []
        for section in (data["assets"], data["liabilities"], data["equity"]):
            rows += [[section.title, r.account.code, r.account.name, r.amount] for r in section.rows]
            rows += [[section.title, "", name, amount] for name, amount in section.extra]
            rows.append([section.title, "", f"Total {section.title.lower()}", section.total])
        return _csv(f"balance-sheet-{currency}-{as_at}.csv", ["Section", "Code", "Account", "Amount"], rows)
    return _page(
        request,
        "accounting/balance_sheet.html",
        "Balance sheet",
        currency=currency,
        as_at=as_at,
        bs=data,
        safeguarding=reports.safeguarding(currency) if as_at == business_date() else None,
    )


@REPORTS
def income_statement(request):
    currency = _currency(request)
    start, end = _period(request)
    data = reports.income_statement(currency, start, end)
    if request.GET.get("export") == "csv":
        rows = [["Income", r.account.code, r.account.name, r.amount] for r in data["income"].rows]
        rows += [["Expenses", r.account.code, r.account.name, r.amount] for r in data["expenses"].rows]
        rows.append(["", "", "Profit (loss)", data["profit"]])
        return _csv(f"income-statement-{currency}-{start}-{end}.csv", ["Section", "Code", "Account", "Amount"], rows)
    return _page(
        request,
        "accounting/income_statement.html",
        "Income statement",
        currency=currency,
        start=start,
        end=end,
        pl=data,
    )


@REPORTS
def ledger(request):
    start, end = _period(request)
    accounts = LedgerAccount.objects.order_by("currency", "code")
    chosen = request.GET.get("account", "")
    account = accounts.filter(pk=chosen).first() if chosen.isdigit() else None
    data = reports.general_ledger(account, start, end) if account else None
    if account and request.GET.get("export") == "csv":
        rows = [["", "", "Opening balance", "", "", data["opening"]]]
        rows += [
            [r["line"].entry.date, r["line"].entry.number, r["line"].description or r["line"].entry.memo,
             r["line"].debit or "", r["line"].credit or "", r["balance"]]
            for r in data["rows"]
        ]  # fmt: skip
        rows.append(["", "", "Closing balance", data["total_debit"], data["total_credit"], data["closing"]])
        return _csv(
            f"ledger-{account.code}-{account.currency}-{start}-{end}.csv",
            ["Date", "Journal", "Description", "Debit", "Credit", "Balance"],
            rows,
        )
    return _page(
        request,
        "accounting/ledger.html",
        "General ledger",
        accounts=accounts,
        account=account,
        start=start,
        end=end,
        gl=data,
    )


@REPORTS
def cashbook(request):
    start, end = _period(request)
    banks = BankAccount.objects.order_by("name")
    bank = banks.filter(pk=request.GET.get("bank")).first() if request.GET.get("bank", "").isdigit() else banks.first()
    data = reports.cashbook(bank, start, end) if bank else None
    if bank and request.GET.get("export") == "csv":
        rows = [["", "", "Opening balance", "", "", "", data["opening"]]]
        for r in data["rows"]:
            e = r["entry"]
            receipt = e.amount if e.direction == CashbookEntry.Direction.RECEIPT else ""
            payment = e.amount if e.direction == CashbookEntry.Direction.PAYMENT else ""
            rows.append([e.date, e.number, e.counterparty, e.get_category_display(), receipt, payment, r["balance"]])
        rows.append(["", "", "Closing balance", "", data["receipts"], data["payments"], data["closing"]])
        return _csv(
            f"cashbook-{bank.ledger_account.code}-{start}-{end}.csv",
            ["Date", "Number", "Counterparty", "Category", "Money in", "Money out", "Balance"],
            rows,
        )
    return _page(request, "accounting/cashbook.html", "Cashbook", banks=banks, bank=bank, start=start, end=end, cb=data)


@REPORTS
def safeguarding(request):
    currency = _currency(request)
    return _page(
        request,
        "accounting/safeguarding.html",
        "Safeguarding check",
        currency=currency,
        sg=reports.safeguarding(currency),
    )


@RECONCILE
def reconcile(request):
    banks = BankAccount.objects.filter(is_active=True).order_by("name")
    source = request.POST if request.method == "POST" else request.GET
    bank = banks.filter(pk=source.get("bank")).first() if str(source.get("bank", "")).isdigit() else None
    statement_date = parse_date(source.get("statement_date") or "") or business_date()
    raw_balance = (source.get("statement_balance") or "").replace(",", "").strip()
    try:
        statement_balance = Decimal(raw_balance) if raw_balance else None
    except InvalidOperation:
        statement_balance = None
        messages.error(request, "Enter the closing balance exactly as it appears on the bank statement.")

    if request.method == "POST" and bank and statement_balance is not None:
        try:
            rec = reconcile_bank(
                staff=request.user,
                bank=bank,
                statement_date=statement_date,
                statement_balance=statement_balance,
                cleared_ids=request.POST.getlist("cleared"),
            )
        except BusinessError as exc:
            messages.error(request, str(exc.detail))
        else:
            messages.success(
                request,
                f"{bank.name} reconciled at {statement_date:%d %b %Y}: {rec.entries_cleared} entries matched to the statement.",
            )
            return HttpResponseRedirect(reverse("admin:accounting_bankreconciliation_changelist"))

    entries = []
    if bank:
        entries = list(
            bank.entries.filter(date__lte=statement_date, cleared_on__isnull=True).order_by("date", "created_at")
        )
    return _page(
        request,
        "accounting/reconcile.html",
        "Reconcile a bank account",
        banks=banks,
        bank=bank,
        statement_date=statement_date,
        statement_balance=raw_balance,
        entries=entries,
        cashbook_balance=bank_balance(bank, statement_date) if bank else None,
        ticked=set(request.POST.getlist("cleared")),
    )


@REPORTS
def business_books(request):
    """One business's own books as FluxPay staff see them: cashbook, profit and loss, balance sheet."""
    from accounting import business as books
    from banking.models import Account
    from organizations.models import Organization

    organizations = Organization.objects.order_by("name")
    chosen = request.GET.get("organization", "")
    organization = organizations.filter(pk=chosen).first() if chosen else None
    start, end = _period(request)
    context = {"organizations": organizations, "organization": organization, "start": start, "end": end}
    if organization:
        wallets = list(Account.objects.filter(organization=organization).order_by("created_at"))
        wallet = next((w for w in wallets if str(w.pk) == request.GET.get("wallet")), wallets[0] if wallets else None)
        if wallet:
            currency = wallet.currency
            cb = books.cashbook(organization, wallet, start, end)
            if request.GET.get("export") == "csv":
                rows = [["", "", "Opening balance", "", "", "", cb["opening"]]]
                for r in cb["rows"]:
                    e = r["entry"]
                    rows.append([e.date, e.counterparty, e.description, e.category.name,
                                 e.amount if e.direction == "IN" else "", e.amount if e.direction == "OUT" else "",
                                 r["balance"]])  # fmt: skip
                rows.append(["", "", "Closing balance", "", cb["money_in"], cb["money_out"], cb["closing"]])
                return _csv(
                    f"{organization.name}-cashbook-{start}-{end}.csv".replace(" ", "-"),
                    ["Date", "Counterparty", "Description", "Category", "Money in", "Money out", "Balance"],
                    rows,
                )
            context.update(
                wallets=wallets,
                wallet=wallet,
                currency=currency,
                cb=cb,
                pl=reports.income_statement(currency, start, end, organization=organization),
                bs=reports.balance_sheet(currency, end, organization=organization),
                workers=organization.workers.filter(is_active=True).count(),
            )
    title = f"{organization.name} – books" if organization else "Business books"
    return _page(request, "accounting/business_books.html", title, **context)
