"""Each business's own books: its cashbook, capital, revenue, expenses, profit and balance sheet.

A business's "bank" is its FluxPay business wallet, so its cashbook is every movement on that wallet,
written here automatically as it happens (banking.services and payroll call `record_movement`) with a
balanced journal in the business's own set of books:

    money in   Dr Wallet (asset)        Cr Sales / Capital / Other income ...
    money out  Dr Salaries / Suppliers / Drawings ...   Cr Wallet (asset)

So the cashbook's running balance always equals the wallet balance. The business may change an entry's
category later (e.g. a receipt was capital, not a sale); that posts a reclassification journal between the
two categories and leaves the money and the cashbook as they were.
"""

from datetime import date as Date
from decimal import Decimal

from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.db.models import Max, Q, Sum

from audit.services import record
from fluxpay.exceptions import BusinessError

from .models import ZERO, BusinessEntry, JournalEntry, LedgerAccount
from .services import business_date, post_journal

T = LedgerAccount.Type
Source = BusinessEntry.Source

# role: (code, name, type, description)
CHART = {
    "capital": ("3000", "Owner's capital", T.EQUITY, "Money the owners put into the business."),
    "drawings": ("3100", "Owner's drawings", T.EQUITY, "Money the owners took out of the business."),
    "sales": ("4000", "Sales and revenue", T.INCOME, "Money customers paid the business."),
    "other_income": ("4900", "Other income", T.INCOME, ""),
    "salaries": ("5000", "Salaries and wages", T.EXPENSE, "Pay to workers, through FluxPay payroll."),
    "suppliers": ("5100", "Purchases and suppliers", T.EXPENSE, "Stock, materials and supplier payments."),
    "expenses": ("5900", "Other business expenses", T.EXPENSE, "Rent, transport, utilities and other costs."),
}
# What a movement is booked to unless someone chooses otherwise.
DEFAULT_IN, DEFAULT_OUT = "sales", "suppliers"


def category(organization, role: str, currency: str) -> LedgerAccount:
    """The business's account for `role`, created from CHART the first time it is needed."""
    account = LedgerAccount.objects.filter(organization=organization, role=role, currency=currency).first()
    if account is not None:
        return account
    code, name, type_, description = CHART[role]
    try:
        with db_transaction.atomic():
            return LedgerAccount.objects.create(
                organization=organization, role=role, currency=currency, code=code, name=name, type=type_,
                description=description,
            )  # fmt: skip
    except IntegrityError:
        return LedgerAccount.objects.get(organization=organization, role=role, currency=currency)


def wallet_account(wallet) -> LedgerAccount:
    """The asset account that mirrors one business wallet (1000, 1001, ...)."""
    role = f"wallet:{wallet.pk}"
    account = LedgerAccount.objects.filter(organization_id=wallet.organization_id, role=role).first()
    if account is not None:
        return account
    with db_transaction.atomic():
        used = LedgerAccount.objects.filter(
            organization_id=wallet.organization_id, currency=wallet.currency, code__regex=r"^10[0-9][0-9]$"
        ).aggregate(top=Max("code"))["top"]
        return LedgerAccount.objects.create(
            organization_id=wallet.organization_id,
            role=role,
            currency=wallet.currency,
            code=str(int(used) + 1) if used else "1000",
            name=f"FluxPay wallet {wallet.account_number}",
            type=T.ASSET,
            is_control=True,
            description="Mirrors the business wallet: every movement is posted automatically.",
        )


def categories(organization, currency: str):
    """The accounts a business can file money under (income, expenses, capital and drawings)."""
    for role in CHART:
        category(organization, role, currency)
    return LedgerAccount.objects.filter(
        organization=organization, currency=currency, is_control=False, is_active=True
    ).order_by("code")


def add_category(*, organization, currency: str, name: str, type_: str, actor) -> LedgerAccount:
    """A business's own category, e.g. "Transport" (expense) or "Consulting fees" (income)."""
    if type_ not in (T.INCOME, T.EXPENSE):
        raise BusinessError("Choose income or expense.", "invalid_category_type")
    name = name.strip()
    if not name:
        raise BusinessError("Give the category a name.", "name_required")
    if LedgerAccount.objects.filter(organization=organization, currency=currency, name__iexact=name).exists():
        raise BusinessError("There is already a category with that name.", "duplicate_category")
    base = 4000 if type_ == T.INCOME else 5000
    with db_transaction.atomic():
        used = (
            LedgerAccount.objects.filter(organization=organization, currency=currency, type=type_)
            .exclude(role__in=CHART)
            .aggregate(top=Max("code"))["top"]
        )
        code = str(max(int(used) + 1, base + 10) if used and used.isdigit() else base + 10)
        account = LedgerAccount.objects.create(
            organization=organization, currency=currency, code=code, name=name[:120], type=type_
        )
        record(
            "books.category_added", actor=actor, organization_id=organization.pk, target=account,
            metadata={"name": account.name, "type": type_},
        )  # fmt: skip
    return account


def record_movement(
    *,
    wallet,
    direction: str,
    amount: Decimal,
    source: str,
    reference: str = "",
    counterparty: str = "",
    counterparty_account: str = "",
    description: str = "",
    role: str | None = None,
    category_account: LedgerAccount | None = None,
    actor=None,
) -> BusinessEntry:
    """Books one movement on a business wallet. Call inside the transaction that moved the money."""
    organization = wallet.organization
    contra = category_account or category(organization, role or (DEFAULT_IN if direction == "IN" else DEFAULT_OUT), wallet.currency)
    cash = wallet_account(wallet)
    memo = (description or counterparty or source)[:255]
    lines = [(cash, amount, 0, memo), (contra, 0, amount, memo)]
    if direction == BusinessEntry.Direction.OUT:
        lines = [(contra, amount, 0, memo), (cash, 0, amount, memo)]
    journal = post_journal(
        date=business_date(), memo=memo, source=JournalEntry.Source.WALLET, reference=reference,
        created_by=actor, lines=lines,
    )  # fmt: skip
    return BusinessEntry.objects.create(
        organization=organization,
        wallet=wallet,
        date=journal.date,
        direction=direction,
        amount=amount,
        counterparty=counterparty[:150],
        counterparty_account=counterparty_account,
        description=description[:255],
        reference=reference,
        source=source,
        category=contra,
        journal=journal,
    )


def on_transfer(transfer, source, destination, *, out_role: str | None = None) -> None:
    """Books a transfer for whichever side(s) are business wallets. `out_role` files the money going out."""
    from banking.services import holder_name

    if source.organization_id and source.organization_id == destination.organization_id:
        _between_own_wallets(transfer, source, destination)
        return
    if source.organization_id:
        record_movement(
            wallet=source, direction="OUT", amount=transfer.amount, source=Source.TRANSFER, reference=transfer.reference,
            counterparty=holder_name(destination), counterparty_account=destination.account_number,
            description=transfer.note or f"Paid {holder_name(destination)}", role=out_role or DEFAULT_OUT,
            actor=transfer.initiated_by,
        )  # fmt: skip
    if destination.organization_id:
        record_movement(
            wallet=destination, direction="IN", amount=transfer.amount, source=Source.TRANSFER,
            reference=transfer.reference, counterparty=holder_name(source), counterparty_account=source.account_number,
            description=transfer.note or f"Received from {holder_name(source)}",
            role=_incoming_role(destination.organization_id, source),
        )  # fmt: skip


def _incoming_role(organization_id, source) -> str:
    """Money from one of the business's owners is capital; from anyone else it is taken as a sale."""
    from organizations.models import Membership

    if source.organization_id is None and Membership.objects.filter(
        organization_id=organization_id, user_id=source.owner_id, role=Membership.Role.OWNER, is_active=True
    ).exists():
        return "capital"
    return DEFAULT_IN


def _between_own_wallets(transfer, source, destination) -> None:
    memo = transfer.note or f"Moved between wallets {source.account_number} and {destination.account_number}"
    giving, receiving = wallet_account(source), wallet_account(destination)
    journal = post_journal(
        date=business_date(), memo=memo, source=JournalEntry.Source.WALLET, reference=transfer.reference,
        created_by=transfer.initiated_by, lines=[(receiving, transfer.amount, 0, memo), (giving, 0, transfer.amount, memo)],
    )  # fmt: skip
    for wallet, direction, other, contra in ((source, "OUT", destination, receiving), (destination, "IN", source, giving)):
        BusinessEntry.objects.create(
            organization_id=wallet.organization_id, wallet=wallet, date=journal.date, direction=direction,
            amount=transfer.amount, counterparty=f"Own wallet {other.account_number}",
            counterparty_account=other.account_number, description=memo[:255], reference=transfer.reference,
            source=Source.TRANSFER, category=contra, journal=journal,
        )  # fmt: skip


ADJUSTMENT_BOOKING = {
    # kind: (direction, role, source, description)
    "CREDIT": ("IN", "capital", Source.DEPOSIT, "Money paid in at FluxPay"),
    "DEBIT": ("OUT", "capital", Source.CORRECTION, "Correction by FluxPay"),
    "PAYOUT": ("OUT", "drawings", Source.WITHDRAWAL, "Cash withdrawal at FluxPay"),
}


def on_adjustment(adjustment) -> None:
    direction, role, source, description = ADJUSTMENT_BOOKING[adjustment.kind]
    record_movement(
        wallet=adjustment.account, direction=direction, amount=adjustment.amount, source=source,
        reference=adjustment.reference, counterparty="FluxPay", description=description, role=role,
        actor=adjustment.created_by,
    )  # fmt: skip


def reclassify(*, entry: BusinessEntry, new_category: LedgerAccount, actor, note: str = "") -> BusinessEntry:
    """Moves an entry to another category with a journal between the two; the cashbook is unchanged."""
    if new_category.organization_id != entry.organization_id or new_category.currency != entry.wallet.currency:
        raise BusinessError("Choose one of this business's categories.", "invalid_category")
    if new_category.is_control or not new_category.is_active:
        raise BusinessError("That category can't be used.", "invalid_category")
    with db_transaction.atomic():
        entry = BusinessEntry.objects.select_for_update().select_related("category").get(pk=entry.pk)
        old = entry.category
        if old.pk == new_category.pk:
            return entry
        if old.is_control:
            raise BusinessError("Moves between your own wallets can't be re-filed.", "cannot_reclassify")
        memo = f"Re-filed {entry.reference or 'entry'} from {old.name} to {new_category.name}"
        # Money in sits as a credit on its category, money out as a debit: move that balance across.
        lines = [(old, entry.amount, 0, memo), (new_category, 0, entry.amount, memo)]
        if entry.direction == BusinessEntry.Direction.OUT:
            lines = [(new_category, entry.amount, 0, memo), (old, 0, entry.amount, memo)]
        post_journal(
            date=business_date(), memo=memo, source=JournalEntry.Source.MANUAL, reference=entry.reference,
            created_by=actor, lines=lines,
        )  # fmt: skip
        entry.category = new_category
        entry.save(update_fields=["category"])
        record(
            "books.reclassified", actor=actor, organization_id=entry.organization_id, target=entry,
            metadata={"from": old.name, "to": new_category.name, "amount": str(entry.amount), "note": note[:200]},
        )  # fmt: skip
    return entry


def cashbook(organization, wallet, start: Date, end: Date) -> dict:
    """The business cashbook for one wallet: opening balance, each movement with a running balance, closing."""
    entries = BusinessEntry.objects.filter(organization=organization, wallet=wallet)
    before = entries.filter(date__lt=start).aggregate(
        money_in=Sum("amount", filter=_in()), money_out=Sum("amount", filter=_out())
    )
    opening = (before["money_in"] or ZERO) - (before["money_out"] or ZERO)
    balance, rows = opening, []
    for entry in entries.filter(date__gte=start, date__lte=end).select_related("category").order_by("date", "created_at"):
        balance += entry.signed_amount
        rows.append({"entry": entry, "balance": balance})
    money_in = sum((r["entry"].amount for r in rows if r["entry"].direction == "IN"), ZERO)
    return {
        "opening": opening,
        "rows": rows,
        "money_in": money_in,
        "money_out": sum((r["entry"].amount for r in rows), ZERO) - money_in,
        "closing": balance,
    }


def _in():
    return Q(direction=BusinessEntry.Direction.IN)


def _out():
    return Q(direction=BusinessEntry.Direction.OUT)
