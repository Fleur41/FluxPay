"""Financial reports built from the general ledger. All figures are per currency; nothing is converted."""

from dataclasses import dataclass, field
from datetime import date as Date
from decimal import Decimal

from django.db.models import Q, Sum

from banking.models import Account

from .models import ZERO, BankAccount, CashbookEntry, JournalLine, LedgerAccount
from .services import bank_balance, ledger

T = LedgerAccount.Type


@dataclass
class Row:
    account: LedgerAccount
    amount: Decimal  # on the account's normal side (a positive asset, a positive liability, ...)


@dataclass
class Section:
    title: str
    rows: list[Row] = field(default_factory=list)
    extra: list[tuple[str, Decimal]] = field(default_factory=list)  # computed lines, e.g. profit to date

    @property
    def total(self) -> Decimal:
        return sum((r.amount for r in self.rows), ZERO) + sum((amount for _, amount in self.extra), ZERO)


def _totals(
    currency: str, *, start: Date | None = None, end: Date | None = None, organization=None
) -> dict[int, tuple]:
    """account id -> (debits, credits) for lines dated within [start, end], in FluxPay's or one business's books."""
    lines = JournalLine.objects.filter(entry__currency=currency, entry__organization=organization)
    if start:
        lines = lines.filter(entry__date__gte=start)
    if end:
        lines = lines.filter(entry__date__lte=end)
    rows = lines.values("account").annotate(dr=Sum("debit"), cr=Sum("credit"))
    return {r["account"]: (r["dr"] or ZERO, r["cr"] or ZERO) for r in rows}


def _normal(account: LedgerAccount, debits: Decimal, credits: Decimal) -> Decimal:
    return debits - credits if account.debit_normal else credits - debits


def _accounts(currency: str, organization=None):
    return LedgerAccount.objects.filter(currency=currency, organization=organization).order_by("code")


def currencies(organization=None) -> list[str]:
    """Currencies that have books (a ledger account), most used first."""
    accounts = LedgerAccount.objects.filter(organization=organization)
    return list(accounts.values_list("currency", flat=True).distinct().order_by("currency"))


def trial_balance(currency: str, as_at: Date, organization=None) -> dict:
    totals = _totals(currency, end=as_at, organization=organization)
    rows = []
    for account in _accounts(currency, organization):
        dr, cr = totals.get(account.id, (ZERO, ZERO))
        net = dr - cr
        if net:
            rows.append({"account": account, "debit": net if net > 0 else ZERO, "credit": -net if net < 0 else ZERO})
    total_debit = sum((r["debit"] for r in rows), ZERO)
    total_credit = sum((r["credit"] for r in rows), ZERO)
    return {
        "rows": rows,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balanced": total_debit == total_credit,
    }


def income_statement(currency: str, start: Date, end: Date, organization=None) -> dict:
    totals = _totals(currency, start=start, end=end, organization=organization)
    income, expenses = Section("Income"), Section("Expenses")
    for account in _accounts(currency, organization).filter(type__in=[T.INCOME, T.EXPENSE]):
        amount = _normal(account, *totals.get(account.id, (ZERO, ZERO)))
        if amount:
            (income if account.type == T.INCOME else expenses).rows.append(Row(account, amount))
    return {"income": income, "expenses": expenses, "profit": income.total - expenses.total}


def balance_sheet(currency: str, as_at: Date, organization=None) -> dict:
    totals = _totals(currency, end=as_at, organization=organization)
    assets, liabilities, equity = Section("Assets"), Section("Liabilities"), Section("Equity")
    profit = ZERO
    for account in _accounts(currency, organization):
        amount = _normal(account, *totals.get(account.id, (ZERO, ZERO)))
        if account.type == T.INCOME:
            profit += amount
        elif account.type == T.EXPENSE:
            profit -= amount
        elif amount:
            {T.ASSET: assets, T.LIABILITY: liabilities, T.EQUITY: equity}[account.type].rows.append(
                Row(account, amount)
            )
    equity.extra.append(("Profit (loss) to date", profit))
    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "liabilities_and_equity": liabilities.total + equity.total,
        "balanced": assets.total == liabilities.total + equity.total,
    }


def general_ledger(account: LedgerAccount, start: Date, end: Date) -> dict:
    before = JournalLine.objects.filter(account=account, entry__date__lt=start).aggregate(
        dr=Sum("debit"), cr=Sum("credit")
    )
    opening = _normal(account, before["dr"] or ZERO, before["cr"] or ZERO)
    balance, rows = opening, []
    lines = (
        JournalLine.objects.filter(account=account, entry__date__gte=start, entry__date__lte=end)
        .select_related("entry")
        .order_by("entry__date", "entry__created_at", "id")
    )
    for line in lines:
        balance += _normal(account, line.debit, line.credit)
        rows.append({"line": line, "balance": balance})
    return {
        "opening": opening,
        "rows": rows,
        "closing": balance,
        "total_debit": sum((r["line"].debit for r in rows), ZERO),
        "total_credit": sum((r["line"].credit for r in rows), ZERO),
    }


def cashbook(bank: BankAccount, start: Date, end: Date) -> dict:
    opening = bank_balance(bank, start.fromordinal(start.toordinal() - 1))
    balance, rows = opening, []
    entries = bank.entries.filter(date__gte=start, date__lte=end).order_by("date", "created_at")
    for entry in entries:
        balance += entry.signed_amount
        rows.append({"entry": entry, "balance": balance})
    receipts = sum((r["entry"].amount for r in rows if r["entry"].direction == CashbookEntry.Direction.RECEIPT), ZERO)
    return {
        "opening": opening,
        "rows": rows,
        "receipts": receipts,
        "payments": sum((r["entry"].amount for r in rows), ZERO) - receipts,
        "closing": balance,
    }


def safeguarding(currency: str) -> dict:
    """Is every shilling owed to customers backed by money in a customer funds bank account?

    Owed to customers = wallet balances + customer receipts not yet allocated to a wallet.
    Also checks the control account against the wallets themselves (the sub-ledger).
    """
    totals = _totals(currency)

    def balance_of(gl: LedgerAccount) -> Decimal:
        return _normal(gl, *totals.get(gl.id, (ZERO, ZERO)))

    safeguarding_banks = BankAccount.objects.filter(currency=currency, purpose=BankAccount.Purpose.SAFEGUARDING)
    banks = [
        {"bank": b, "balance": balance_of(b.ledger_account)}
        for b in safeguarding_banks.select_related("ledger_account")
    ]
    held = sum((b["balance"] for b in banks), ZERO)
    customer_funds = balance_of(ledger("customer_funds", currency))
    unallocated = balance_of(ledger("unallocated_receipts", currency))
    owed = customer_funds + unallocated
    wallets = Account.objects.filter(system_key__isnull=True, currency=currency).aggregate(
        personal=Sum("balance", filter=Q(organization__isnull=True)),
        business=Sum("balance", filter=Q(organization__isnull=False)),
    )
    personal, business = wallets["personal"] or ZERO, wallets["business"] or ZERO
    return {
        "currency": currency,
        "banks": banks,
        "held": held,
        "customer_funds": customer_funds,
        "unallocated": unallocated,
        "owed": owed,
        "surplus": held - owed,
        "backed": held >= owed,
        "personal_wallets": personal,
        "business_wallets": business,
        "wallets_total": personal + business,
        "subledger_difference": customer_funds - (personal + business),
    }
