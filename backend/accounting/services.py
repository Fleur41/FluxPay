"""Posting to FluxPay's books. Every journal goes through post_journal, inside the caller's DB transaction.

Locking order (to avoid deadlocks): cashbook entry rows, then wallet accounts, then document-number
sequences (PAY, then RCT, then JE), then the audit chain head (audit.services.record) last.
"""

from datetime import date as Date
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.db.models import Max, Q, Sum
from django.utils import timezone
from rest_framework import status

from audit.services import record
from fluxpay.exceptions import BusinessError

from .models import (
    ZERO,
    AccountingSettings,
    BankAccount,
    BankReconciliation,
    CashbookEntry,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    Sequence,
)

T = LedgerAccount.Type
Category = CashbookEntry.Category
Direction = CashbookEntry.Direction

# role: (code, name, type, is_control, description)
CHART = {
    "customer_funds": (
        "2000",
        "Customer wallet balances",
        T.LIABILITY,
        True,
        "What FluxPay owes its customers and businesses: the total of every wallet.",
    ),
    "unallocated_receipts": (
        "2100",
        "Unallocated customer receipts",
        T.LIABILITY,
        True,
        "Customer money received in the bank but not yet credited to a wallet.",
    ),
    "capital": ("3000", "Owner's capital", T.EQUITY, False, "Money the owners have put into FluxPay."),
    "drawings": ("3100", "Owner's drawings", T.EQUITY, False, "Money the owners have taken out of FluxPay."),
    "opening_balance": (
        "3200",
        "Opening balances",
        T.EQUITY,
        False,
        "Customer balances that existed before the books started, not backed by money in the bank.",
    ),
    "interest_income": ("4000", "Interest income", T.INCOME, False, "Interest paid by the bank."),
    "other_income": ("4900", "Other income", T.INCOME, False, ""),
    "bank_charges": ("5000", "Bank charges", T.EXPENSE, False, "Fees charged by the bank."),
    "promotions": ("5100", "Customer promotions", T.EXPENSE, False, "Welcome bonuses paid into new wallets."),
    "operating_expenses": ("5900", "Operating expenses", T.EXPENSE, False, "General running costs."),
}
RAIL_CODES = {"PAYPAL": "1210", "BANK": "1220", "MPESA": "1230", "FAKE": "1290"}

DIRECTION = {
    Category.CUSTOMER_DEPOSIT: Direction.RECEIPT,
    Category.CAPITAL: Direction.RECEIPT,
    Category.INTEREST: Direction.RECEIPT,
    Category.OTHER_INCOME: Direction.RECEIPT,
    Category.CUSTOMER_PAYOUT: Direction.PAYMENT,
    Category.BANK_PAYOUT: Direction.PAYMENT,
    Category.BANK_CHARGES: Direction.PAYMENT,
    Category.EXPENSE: Direction.PAYMENT,
    Category.DRAWINGS: Direction.PAYMENT,
    Category.BANK_TRANSFER: Direction.PAYMENT,
}
# The other side of the bank in each kind of entry.
CONTRA_ROLE = {
    Category.CUSTOMER_DEPOSIT: "unallocated_receipts",
    Category.CAPITAL: "capital",
    Category.INTEREST: "interest_income",
    Category.OTHER_INCOME: "other_income",
    Category.CUSTOMER_PAYOUT: "customer_funds",
    # The wallet was already debited into the bank clearing account when the payout was requested.
    Category.BANK_PAYOUT: "provider_clearing:BANK",
    Category.BANK_CHARGES: "bank_charges",
    Category.EXPENSE: "operating_expenses",
    Category.DRAWINGS: "drawings",
}
# Staff may pick a specific income or expense account for these categories.
CHOOSABLE_ACCOUNT = {Category.OTHER_INCOME: T.INCOME, Category.EXPENSE: T.EXPENSE}


# --- Chart of accounts ---------------------------------------------------------------------------


def ledger(role: str, currency: str) -> LedgerAccount:
    """The system account for `role` in `currency`, created from CHART on first use."""
    account = LedgerAccount.objects.filter(role=role, currency=currency, organization__isnull=True).first()
    if account is not None:
        return account
    if role.startswith("provider_clearing:"):
        rail = role.split(":", 1)[1]
        code, name, type_, control, description = (
            RAIL_CODES.get(rail, "1299"),
            f"{rail.title()} clearing",
            T.ASSET,
            True,
            f"Money held for FluxPay by {rail.title()} until it is paid out or settled.",
        )
    else:
        code, name, type_, control, description = CHART[role]
    try:
        with db_transaction.atomic():
            return LedgerAccount.objects.create(
                role=role,
                currency=currency,
                code=code,
                name=name,
                type=type_,
                is_control=control,
                description=description,
            )
    except IntegrityError:
        return LedgerAccount.objects.get(role=role, currency=currency, organization__isnull=True)


def open_bank_account(**fields) -> BankAccount:
    """Creates a bank account and its ledger account (codes 1010, 1011, ... per currency)."""
    currency = fields["currency"]
    with db_transaction.atomic():
        own_banks = LedgerAccount.objects.filter(
            currency=currency, organization__isnull=True, code__regex=r"^10[0-9][0-9]$"
        )
        used = own_banks.aggregate(top=Max("code"))["top"]
        code = str(int(used) + 1) if used else "1010"
        gl = LedgerAccount.objects.create(
            code=code,
            name=fields["name"],
            type=T.ASSET,
            currency=currency,
            is_control=True,
            description=f"{fields['bank_name']} account {fields['account_number']}",
        )
        bank = BankAccount.objects.create(ledger_account=gl, **fields)
        gl.role = f"bank:{bank.pk}"
        gl.save(update_fields=["role"])
    return bank


# --- Dates and numbers ---------------------------------------------------------------------------


def update_bank_account(*, staff, bank: BankAccount, **changes) -> BankAccount:
    """Staff correct a bank account's details. Its account in the books is renamed with it; audited."""
    allowed = {"name", "bank_name", "account_number", "branch", "is_active"}
    with db_transaction.atomic():
        bank = BankAccount.objects.select_for_update().select_related("ledger_account").get(pk=bank.pk)
        before, after = {}, {}
        for field, value in changes.items():
            if field in allowed and getattr(bank, field) != value:
                before[field], after[field] = str(getattr(bank, field)), str(value)
                setattr(bank, field, value)
        if not after:
            return bank
        bank.save(update_fields=list(after))
        if "name" in after and bank.ledger_account.name != bank.name:
            bank.ledger_account.name = bank.name[:120]
            bank.ledger_account.save(update_fields=["name"])
        record("bank_account.changed", actor=staff, target=bank, metadata={"before": before, "after": after})
    return bank


def business_date() -> Date:
    """Today in FluxPay's home time zone (a 1 a.m. deposit in Nairobi belongs to that day, not yesterday's UTC)."""
    return timezone.localdate(timezone.now(), ZoneInfo(settings.FLUXPAY_DISPLAY_TIMEZONE))


def books() -> AccountingSettings:
    return AccountingSettings.objects.get_or_create(id=1)[0]


def date_problem(when: Date, organization=None) -> str | None:
    """Why `when` can't be used as an accounting date, or None. FluxPay's period lock applies to its own books."""
    if when > business_date():
        return "The date can't be in the future."
    if organization is not None:
        return None
    closed = books().books_closed_until
    if closed and when <= closed:
        return f"The books are closed up to {closed:%d %b %Y}. Use a later date, or ask an accountant to reopen them."
    return None


def _next_number(name: str, prefix: str | None = None) -> str:
    Sequence.objects.get_or_create(name=name)
    sequence = Sequence.objects.select_for_update().get(name=name)
    sequence.last += 1
    sequence.save(update_fields=["last"])
    return f"{prefix or name}-{sequence.last:06d}"


# --- Journals ------------------------------------------------------------------------------------


def post_journal(*, date, memo, source, lines, reference="", created_by=None, reverses=None) -> JournalEntry:
    """Posts a balanced entry. `lines` is a list of (LedgerAccount, debit, credit, description)."""
    if len(lines) < 2:
        raise BusinessError("A journal needs at least two lines.", "journal_unbalanced")
    currencies = {account.currency for account, *_ in lines}
    if len(currencies) != 1:
        raise BusinessError("All lines of a journal must be in the same currency.", "journal_currency")
    entities = {account.organization_id for account, *_ in lines}
    if len(entities) != 1:
        raise BusinessError("All lines of a journal must belong to the same set of books.", "journal_entity")
    organization_id = entities.pop()
    total_debit = total_credit = ZERO
    for account, debit, credit, _ in lines:
        debit, credit = Decimal(debit or 0), Decimal(credit or 0)
        if (debit > 0) == (credit > 0) or debit < 0 or credit < 0:
            raise BusinessError("Each line needs either a debit or a credit, not both.", "journal_line")
        if not account.is_active:
            raise BusinessError(f"{account} is inactive.", "journal_account_inactive")
        total_debit += debit
        total_credit += credit
    if total_debit != total_credit:
        raise BusinessError(
            f"Debits ({total_debit:,.2f}) and credits ({total_credit:,.2f}) must be equal.", "journal_unbalanced"
        )
    problem = date_problem(date, organization_id)
    if problem:
        raise BusinessError(problem, "period_closed")

    # Each business numbers its own journals (BJ-000001, ...); FluxPay's run JE-000001, ...
    sequence, prefix = ("JE", "JE") if organization_id is None else (f"B{organization_id.hex[:9]}", "BJ")
    entry = JournalEntry.objects.create(
        organization_id=organization_id,
        number=_next_number(sequence, prefix),
        date=date,
        currency=currencies.pop(),
        memo=memo[:255],
        source=source,
        reference=reference,
        created_by=created_by,
        reverses=reverses,
    )
    JournalLine.objects.bulk_create(
        JournalLine(
            entry=entry,
            account=account,
            debit=Decimal(debit or 0),
            credit=Decimal(credit or 0),
            description=(description or "")[:255],
        )
        for account, debit, credit, description in lines
    )
    return entry


def _reversal_of(entry: JournalEntry, *, staff, memo: str) -> JournalEntry:
    if hasattr(entry, "reversed_by"):
        raise BusinessError(f"{entry.number} has already been reversed.", "already_reversed")
    return post_journal(
        date=business_date(),
        memo=memo,
        source=JournalEntry.Source.REVERSAL,
        reference=entry.reference or entry.number,
        created_by=staff,
        reverses=entry,
        lines=[(line.account, line.credit, line.debit, line.description) for line in entry.lines.all()],
    )


def post_manual_journal(*, staff, date, memo, lines) -> JournalEntry:
    """An accountant's journal (accruals, reclassifications). Control accounts are off limits."""
    for account, *_ in lines:
        if account.is_control:
            raise BusinessError(
                f"{account.code} {account.name} is a control account: it is only posted through "
                "the cashbook or wallets.",
                "control_account",
            )
    with db_transaction.atomic():
        entry = post_journal(date=date, memo=memo, source=JournalEntry.Source.MANUAL, lines=lines, created_by=staff)
        record("journal.posted", actor=staff, target=entry, metadata={"number": entry.number, "memo": memo})
    return entry


def reverse_manual_journal(*, staff, entry: JournalEntry, reason: str) -> JournalEntry:
    if entry.source != JournalEntry.Source.MANUAL:
        raise BusinessError(
            "Only manual journals are reversed here. Reverse a cashbook entry from the cashbook, and fix a wallet "
            "with a correction.",
            "not_manual",
        )
    with db_transaction.atomic():
        entry = JournalEntry.objects.select_for_update().get(pk=entry.pk)
        reversal = _reversal_of(entry, staff=staff, memo=f"Reversal of {entry.number}: {reason}")
        record("journal.reversed", actor=staff, target=entry, metadata={"reversal": reversal.number, "reason": reason})
    return reversal


# --- Wallet activity -----------------------------------------------------------------------------


def book_wallet_movement(*, role, currency, amount, into_wallets: bool, memo: str, reference: str) -> JournalEntry:
    """Mirrors money crossing into (or out of) the wallets, so the control account always equals their total.

    `role` is where the money came from or went: "promotions", "provider_clearing:PAYPAL", ...
    """
    other, customers = ledger(role, currency), ledger("customer_funds", currency)
    lines = [(other, amount, 0, memo), (customers, 0, amount, memo)]
    if not into_wallets:
        lines = [(customers, amount, 0, memo), (other, 0, amount, memo)]
    return post_journal(
        date=business_date(), memo=memo, source=JournalEntry.Source.WALLET, reference=reference, lines=lines
    )


def lock_entry(entry_id) -> CashbookEntry:
    return CashbookEntry.objects.select_for_update().select_related("bank_account", "created_by").get(pk=entry_id)


def allocation_problem(entry: CashbookEntry, *, kind: str, amount: Decimal, wallet, staff) -> str | None:
    """Why a top-up (CREDIT) or correction (DEBIT) can't use this receipt, or None. `entry` should be locked."""
    if entry.category != Category.CUSTOMER_DEPOSIT:
        return "Choose a customer deposit receipt from the cashbook."
    if entry.is_reversed:
        return f"{entry.number} has been reversed."
    if wallet is not None and wallet.currency != entry.bank_account.currency:
        return f"{entry.number} is in {entry.bank_account.currency}; the wallet is in {wallet.currency}."
    if kind == "CREDIT":
        if amount > entry.unallocated:
            return f"Only {entry.unallocated:,.2f} {entry.bank_account.currency} of {entry.number} is left to allocate."
        if books().require_second_person and entry.created_by_id == staff.pk:
            return "You recorded this receipt, so a colleague must credit the wallet (segregation of duties)."
    elif amount > entry.allocated:
        return (
            f"Only {entry.allocated:,.2f} {entry.bank_account.currency} of {entry.number} has been allocated, "
            "so no more can be returned to it."
        )
    return None


def book_adjustment(adjustment, entry: CashbookEntry) -> JournalEntry:
    """Books a staff top-up, correction or cash payout. Called by banking.services.post_adjustment."""
    wallet, amount = adjustment.account, adjustment.amount
    currency = wallet.currency
    customers = ledger("customer_funds", currency)
    if adjustment.kind == "PAYOUT":
        bank = entry.bank_account.ledger_account
        memo = f"Cash withdrawal from wallet {wallet.account_number} ({entry.counterparty})"
        journal = post_journal(
            date=entry.date,
            memo=memo,
            source=JournalEntry.Source.CASHBOOK,
            reference=entry.number,
            created_by=adjustment.created_by,
            lines=[(customers, amount, 0, memo), (bank, 0, amount, memo)],
        )
        entry.journal = journal
        entry.save(update_fields=["journal"])
        return journal

    unallocated = ledger("unallocated_receipts", currency)
    if adjustment.kind == "CREDIT":
        memo = f"{entry.number} allocated to wallet {wallet.account_number}"
        lines = [(unallocated, amount, 0, memo), (customers, 0, amount, memo)]
        entry.allocated += amount
    else:
        memo = f"Correction: wallet {wallet.account_number} returned to {entry.number}"
        lines = [(customers, amount, 0, memo), (unallocated, 0, amount, memo)]
        entry.allocated -= amount
    entry.save(update_fields=["allocated"])
    return post_journal(
        date=business_date(),
        memo=memo,
        source=JournalEntry.Source.ALLOCATION,
        reference=adjustment.reference,
        created_by=adjustment.created_by,
        lines=lines,
    )


# --- Cashbook ------------------------------------------------------------------------------------


def bank_balance(bank: BankAccount, as_at: Date | None = None) -> Decimal:
    """The cashbook balance: receipts less payments, up to and including `as_at`."""
    entries = bank.entries.all() if as_at is None else bank.entries.filter(date__lte=as_at)
    totals = entries.aggregate(
        receipts=Sum("amount", filter=Q(direction=Direction.RECEIPT)),
        payments=Sum("amount", filter=Q(direction=Direction.PAYMENT)),
    )
    return (totals["receipts"] or ZERO) - (totals["payments"] or ZERO)


def cashbook_problems(
    *, bank, category, amount, date, ledger_account=None, wallet=None, transfer_to=None
) -> dict[str, str]:
    """Field -> message for everything wrong with a proposed cashbook entry (empty when it can be posted)."""
    problems = {}
    if category not in DIRECTION:
        problems["category"] = "Choose what the money was for."
        return problems
    if bank is not None and not bank.is_active:
        problems["bank_account"] = "This bank account is closed."
    if amount is not None and amount <= 0:
        problems["amount"] = "Enter an amount above zero."
    if date is not None and (problem := date_problem(date)):
        problems["date"] = problem
    if bank is None or amount is None:
        return problems

    if category in (Category.CUSTOMER_DEPOSIT, Category.CUSTOMER_PAYOUT) and (
        bank.purpose != BankAccount.Purpose.SAFEGUARDING
    ):
        problems["bank_account"] = "Customer money must go through a customer funds (safeguarding) bank account."
    if category == Category.CUSTOMER_PAYOUT:
        if wallet is not None:
            wallet = type(wallet).objects.get(pk=wallet.pk)  # the current balance, not a stale copy
        if wallet is None:
            problems["wallet"] = "Choose the wallet the customer is withdrawing from."
        elif wallet.currency != bank.currency:
            problems["wallet"] = f"The wallet is in {wallet.currency}; the bank account is in {bank.currency}."
        elif not wallet.is_active:
            problems["wallet"] = "This wallet is closed."
        elif wallet.balance < amount:
            problems["amount"] = f"The wallet only holds {wallet.balance:,.2f} {wallet.currency}."
    if category in CHOOSABLE_ACCOUNT and ledger_account is not None:
        if ledger_account.type != CHOOSABLE_ACCOUNT[category] or ledger_account.currency != bank.currency:
            problems["ledger_account"] = (
                f"Choose an {CHOOSABLE_ACCOUNT[category].label.lower()} account in {bank.currency}."
            )
        elif ledger_account.is_control or not ledger_account.is_active:
            problems["ledger_account"] = "That account can't be used here."
    if category == Category.BANK_TRANSFER:
        if transfer_to is None:
            problems["transfer_to"] = "Choose the bank account the money went to."
        elif transfer_to.pk == bank.pk:
            problems["transfer_to"] = "Choose a different bank account."
        elif transfer_to.currency != bank.currency:
            problems["transfer_to"] = "Both bank accounts must be in the same currency."
        elif not transfer_to.is_active:
            problems["transfer_to"] = "That bank account is closed."
    if DIRECTION[category] == Direction.PAYMENT and "amount" not in problems:
        available = bank_balance(bank)
        if amount > available:
            problems["amount"] = (
                f"The cashbook shows only {available:,.2f} {bank.currency} in {bank.name}. "
                "Record the money coming in first."
            )
    return problems


def record_cashbook_entry(
    *,
    staff,
    bank,
    category,
    amount: Decimal,
    date: Date,
    counterparty: str,
    description: str,
    bank_reference: str = "",
    ledger_account=None,
    wallet=None,
    transfer_to=None,
) -> CashbookEntry:
    """Records money that moved in a FluxPay bank account and posts its journal."""
    problems = cashbook_problems(
        bank=bank,
        category=category,
        amount=amount,
        date=date,
        ledger_account=ledger_account,
        wallet=wallet,
        transfer_to=transfer_to,
    )
    if problems:
        raise BusinessError(" ".join(problems.values()), "cashbook_invalid")
    direction = DIRECTION[category]
    fields = {
        "bank_account": bank,
        "direction": direction,
        "category": category,
        "date": date,
        "amount": amount,
        "counterparty": counterparty.strip(),
        "bank_reference": bank_reference.strip(),
        "description": description.strip(),
        "created_by": staff,
    }

    with db_transaction.atomic():
        if category == Category.CUSTOMER_PAYOUT:
            from banking.services import post_adjustment

            entry = CashbookEntry.objects.create(number=_next_number("PAY"), **fields)
            # Debits the wallet (locked there) and books Dr customer funds / Cr bank via book_adjustment.
            post_adjustment(
                staff=staff,
                account_id=wallet.id,
                kind="PAYOUT",
                amount=amount,
                reason=f"{entry.number}: {description}",
                cashbook_entry=entry,
            )
            entry.refresh_from_db()  # book_adjustment attached the journal to its locked copy
        elif category == Category.BANK_TRANSFER:
            entry = CashbookEntry.objects.create(number=_next_number("PAY"), **fields)
            incoming = CashbookEntry.objects.create(
                number=_next_number("RCT"),
                **{**fields, "bank_account": transfer_to, "direction": Direction.RECEIPT, "counterparty": bank.name},
            )
            memo = f"Transfer from {bank.name} to {transfer_to.name}"
            journal = post_journal(
                date=date,
                memo=memo,
                source=JournalEntry.Source.CASHBOOK,
                reference=entry.number,
                created_by=staff,
                lines=[(transfer_to.ledger_account, amount, 0, memo), (bank.ledger_account, 0, amount, memo)],
            )
            entry.counterpart, incoming.counterpart = incoming, entry
            entry.journal = incoming.journal = journal
            entry.save(update_fields=["counterpart", "journal"])
            incoming.save(update_fields=["counterpart", "journal"])
        else:
            prefix = "RCT" if direction == Direction.RECEIPT else "PAY"
            if category in CHOOSABLE_ACCOUNT:
                fields["ledger_account"] = ledger_account or ledger(CONTRA_ROLE[category], bank.currency)
            entry = CashbookEntry.objects.create(number=_next_number(prefix), **fields)
            contra = fields.get("ledger_account") or ledger(CONTRA_ROLE[category], bank.currency)
            memo = f"{entry.get_category_display()}: {entry.counterparty}"
            if direction == Direction.RECEIPT:  # Dr Bank, Cr where it came from
                lines = [(bank.ledger_account, amount, 0, memo), (contra, 0, amount, memo)]
            else:  # Dr what it paid for, Cr Bank
                lines = [(contra, amount, 0, memo), (bank.ledger_account, 0, amount, memo)]
            entry.journal = post_journal(
                date=date,
                memo=memo,
                source=JournalEntry.Source.CASHBOOK,
                reference=entry.number,
                created_by=staff,
                lines=lines,
            )
            entry.save(update_fields=["journal"])
        record(
            "cashbook.receipt" if direction == Direction.RECEIPT else "cashbook.payment",
            actor=staff,
            target=entry,
            metadata={
                "number": entry.number,
                "bank": bank.name,
                "category": category,
                "amount": str(amount),
                "currency": bank.currency,
                "counterparty": entry.counterparty,
            },
        )
    return entry


def reversal_problem(entry: CashbookEntry) -> str | None:
    if entry.category == Category.REVERSAL:
        return "This entry is itself a reversal."
    if entry.is_reversed:
        return f"{entry.number} has already been reversed."
    if entry.category == Category.CUSTOMER_PAYOUT:
        return (
            "A cash withdrawal can't be reversed, because the customer's wallet was debited. If the money came back, "
            "record it as a customer deposit and allocate it to the wallet."
        )
    if entry.category == Category.CUSTOMER_DEPOSIT and entry.allocated > 0:
        return (
            f"{entry.allocated:,.2f} of {entry.number} has been credited to wallets. Take it back with corrections "
            "first, then reverse the receipt."
        )
    return None


def reverse_cashbook_entry(*, staff, entry: CashbookEntry, reason: str) -> CashbookEntry:
    """Cancels a wrongly recorded entry (both halves of a bank transfer) with opposite entries dated today."""
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise BusinessError("Give a reason of at least 10 characters for the audit trail.", "reason_required")
    with db_transaction.atomic():
        ids = [entry.pk] + ([entry.counterpart_id] if entry.counterpart_id else [])
        locked = {e.pk: e for e in CashbookEntry.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
        entry = locked[entry.pk]
        problem = reversal_problem(entry)
        if problem:
            raise BusinessError(problem, "cannot_reverse")
        reversals = []
        # Receipts first: their reversals take PAY numbers, which are always taken before RCT (lock order).
        for original in sorted(locked.values(), key=lambda e: e.direction != Direction.RECEIPT):
            # Reversing a receipt is a payment out of the cashbook, and vice versa.
            opposite = Direction.PAYMENT if original.direction == Direction.RECEIPT else Direction.RECEIPT
            reversals.append(
                CashbookEntry.objects.create(
                    number=_next_number("PAY" if opposite == Direction.PAYMENT else "RCT"),
                    bank_account=original.bank_account,
                    direction=opposite,
                    category=Category.REVERSAL,
                    date=business_date(),
                    amount=original.amount,
                    counterparty=original.counterparty,
                    bank_reference=original.bank_reference,
                    description=f"Reversal of {original.number}: {reason}"[:255],
                    created_by=staff,
                    reverses=original,
                )
            )
        journal = _reversal_of(entry.journal, staff=staff, memo=f"Reversal of {entry.number}: {reason}")
        if len(reversals) == 2:
            reversals[0].counterpart, reversals[1].counterpart = reversals[1], reversals[0]
        for reversal in reversals:
            reversal.journal = journal
            reversal.save(update_fields=["journal", "counterpart"])
        record(
            "cashbook.reversed",
            actor=staff,
            target=entry,
            metadata={"number": entry.number, "reversal": reversals[0].number, "reason": reason},
        )
    return next(r for r in reversals if r.reverses_id == entry.pk)


# --- Bank reconciliation -------------------------------------------------------------------------


def reconcile_bank(*, staff, bank, statement_date: Date, statement_balance: Decimal, cleared_ids) -> BankReconciliation:
    """Marks the entries that appear on the statement as cleared and saves the signed-off reconciliation.

    Balance per bank statement + receipts not yet on the statement - payments not yet on the statement
    must equal the cashbook balance at the statement date, to the cent.
    """
    if statement_date > business_date():
        raise BusinessError("The statement date can't be in the future.", "date_in_future")
    with db_transaction.atomic():
        open_entries = CashbookEntry.objects.select_for_update().filter(
            bank_account=bank, date__lte=statement_date, cleared_on__isnull=True
        )
        cleared_ids = {str(i) for i in cleared_ids}
        to_clear = [e for e in open_entries if str(e.pk) in cleared_ids]
        uncleared = [e for e in open_entries if str(e.pk) not in cleared_ids]
        receipts = sum((e.amount for e in uncleared if e.direction == Direction.RECEIPT), ZERO)
        payments = sum((e.amount for e in uncleared if e.direction == Direction.PAYMENT), ZERO)
        cashbook = bank_balance(bank, statement_date)
        difference = statement_balance + receipts - payments - cashbook
        if difference != 0:
            raise BusinessError(
                f"The reconciliation is out by {difference:,.2f} {bank.currency}. Tick the entries that appear on "
                "the statement, and check for bank charges or receipts not yet in the cashbook.",
                "reconciliation_difference",
                status.HTTP_400_BAD_REQUEST,
            )
        CashbookEntry.objects.filter(pk__in=[e.pk for e in to_clear]).update(cleared_on=statement_date)
        reconciliation = BankReconciliation.objects.create(
            bank_account=bank,
            statement_date=statement_date,
            statement_balance=statement_balance,
            cashbook_balance=cashbook,
            uncleared_receipts=receipts,
            uncleared_payments=payments,
            entries_cleared=len(to_clear),
            prepared_by=staff,
        )
        record(
            "bank.reconciled",
            actor=staff,
            target=reconciliation,
            metadata={
                "bank": bank.name,
                "statement_date": statement_date.isoformat(),
                "statement_balance": str(statement_balance),
                "entries_cleared": len(to_clear),
            },
        )
    return reconciliation
