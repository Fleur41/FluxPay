"""Bills (money the business owes: payables) and invoices (money owed to it: receivables).

The cashbook stays the only place money moves. A bill or invoice books the expense or income when it is
recorded, against Accounts payable or Accounts receivable:

    bill      Dr Expense category        Cr Accounts payable
    invoice   Dr Accounts receivable     Cr Income category

It is paid by linking a cashbook entry to it: the real payment out (for a bill) or money received (for an
invoice). That entry was booked to a category when the money moved; linking moves it to payables or
receivables, so the expense or income isn't counted twice:

    bill paid        Dr Accounts payable     Cr <the entry's category>   (net: Dr Payable, Cr Wallet)
    invoice paid     Dr <the entry's category>   Cr Accounts receivable  (net: Dr Wallet, Cr Receivable)

Payables and receivables are control accounts: nobody files an entry there by hand, so what they show is
always exactly what's outstanding.
"""

from datetime import date as Date
from decimal import Decimal

from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.utils import timezone

from audit.services import record
from fluxpay.exceptions import BusinessError

from .models import BusinessEntry, Invoice, InvoicePayment, JournalEntry, LedgerAccount
from .services import business_date, post_journal

T = LedgerAccount.Type
Kind = Invoice.Kind
Status = Invoice.Status

# role: (code, name, type, description)
CONTROL = {
    "receivables": ("1200", "Accounts receivable", T.ASSET, "Money customers owe the business (open invoices)."),
    "payables": ("2000", "Accounts payable", T.LIABILITY, "Money the business owes suppliers (open bills)."),
}
# A bill is an expense; an invoice is income. Which side of the cashbook pays each.
CATEGORY_TYPE = {Kind.BILL: T.EXPENSE, Kind.INVOICE: T.INCOME}
PAID_BY = {Kind.BILL: BusinessEntry.Direction.OUT, Kind.INVOICE: BusinessEntry.Direction.IN}
CONTROL_ROLE = {Kind.BILL: "payables", Kind.INVOICE: "receivables"}
PREFIX = {Kind.BILL: "BILL", Kind.INVOICE: "INV"}


def control_account(organization, role: str, currency: str) -> LedgerAccount:
    """The business's Accounts payable or receivable, created the first time it is needed."""
    account = LedgerAccount.objects.filter(organization=organization, role=role, currency=currency).first()
    if account is not None:
        return account
    code, name, type_, description = CONTROL[role]
    try:
        with db_transaction.atomic():
            return LedgerAccount.objects.create(
                organization=organization, role=role, currency=currency, code=code, name=name, type=type_,
                description=description, is_control=True,
            )  # fmt: skip
    except IntegrityError:
        return LedgerAccount.objects.get(organization=organization, role=role, currency=currency)


def create(*, organization, kind: str, party: str, amount: Decimal, category: LedgerAccount, currency: str,
           actor, description: str = "", issue_date: Date | None = None, due_date: Date | None = None) -> Invoice:  # fmt: skip
    party = party.strip()
    if not party:
        raise BusinessError("Who is it from or to? Give the supplier's or customer's name.", "party_required")
    if amount <= 0:
        raise BusinessError("Enter an amount above zero.", "invalid_amount")
    if category.organization_id != organization.pk or category.currency != currency or category.is_control:
        raise BusinessError("Choose one of this business's categories.", "invalid_category")
    if category.type != CATEGORY_TYPE[kind]:
        what = "an expense" if kind == Kind.BILL else "an income"
        raise BusinessError(f"A {Kind(kind).label.lower()} goes under {what} category.", "invalid_category")
    issue_date = issue_date or business_date()
    if due_date and due_date < issue_date:
        raise BusinessError("The due date can't be before the date it was issued.", "invalid_due_date")

    from organizations.models import Organization

    with db_transaction.atomic():
        Organization.objects.select_for_update().get(pk=organization.pk)  # one number at a time per business
        count = Invoice.objects.filter(organization=organization, kind=kind).count()
        number = f"{PREFIX[kind]}-{count + 1:04d}"
        control = control_account(organization, CONTROL_ROLE[kind], currency)
        memo = f"{number} {party}" + (f": {description}" if description else "")
        if kind == Kind.BILL:
            lines = [(category, amount, 0, memo), (control, 0, amount, memo)]
        else:
            lines = [(control, amount, 0, memo), (category, 0, amount, memo)]
        journal = post_journal(
            date=issue_date, memo=memo[:255], source=JournalEntry.Source.MANUAL, reference=number,
            created_by=actor, lines=lines,
        )  # fmt: skip
        invoice = Invoice.objects.create(
            organization=organization, kind=kind, number=number, party=party[:150], description=description[:255],
            category=category, currency=currency, amount=amount, issue_date=issue_date, due_date=due_date,
            journal=journal, created_by=actor,
        )  # fmt: skip
        record(
            f"books.{kind.lower()}_recorded", actor=actor, organization_id=organization.pk, target=invoice,
            metadata={"number": number, "party": invoice.party, "amount": str(amount), "category": category.name},
        )  # fmt: skip
    return invoice


def payable_entries(invoice: Invoice):
    """Cashbook entries that could pay this bill (or collect this invoice): the right direction, not already
    linked to one, filed under an ordinary category, and no more than what's still outstanding."""
    return (
        BusinessEntry.objects.filter(
            organization_id=invoice.organization_id,
            wallet__currency=invoice.currency,
            direction=PAID_BY[invoice.kind],
            amount__lte=invoice.outstanding,
            invoice_payment__isnull=True,
            category__is_control=False,
        )
        .select_related("category")
        .order_by("-date", "-created_at")
    )


def pay(*, invoice: Invoice, entry: BusinessEntry, actor) -> Invoice:
    """Links a cashbook entry to the bill or invoice it pays, and moves it to payables/receivables."""
    with db_transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        entry = BusinessEntry.objects.select_for_update().select_related("category", "wallet").get(pk=entry.pk)
        label = Kind(invoice.kind).label.lower()
        if invoice.status in (Status.PAID, Status.CANCELLED):
            raise BusinessError(f"This {label} is already {invoice.get_status_display().lower()}.", "invoice_closed")
        if entry.organization_id != invoice.organization_id or entry.wallet.currency != invoice.currency:
            raise BusinessError("That cashbook entry isn't from this business.", "entry_not_found", 404)
        if entry.direction != PAID_BY[invoice.kind]:
            needed = "a payment out" if invoice.kind == Kind.BILL else "money received"
            raise BusinessError(f"A {label} is paid by {needed}.", "wrong_direction")
        if InvoicePayment.objects.filter(entry=entry).exists():
            raise BusinessError("That entry already pays another bill or invoice.", "entry_already_linked")
        if entry.category.is_control:
            raise BusinessError("That entry can't be linked.", "entry_not_linkable")
        if entry.amount > invoice.outstanding:
            raise BusinessError(
                f"That entry is {entry.amount:,.2f} but only {invoice.outstanding:,.2f} is still owed on "
                f"{invoice.number}. Link a smaller payment, or correct the {label}.",
                "overpayment",
            )
        control = control_account(invoice.organization, CONTROL_ROLE[invoice.kind], invoice.currency)
        old = entry.category
        memo = f"{entry.reference or 'Entry'} pays {invoice.number} ({invoice.party})"
        if invoice.kind == Kind.BILL:
            lines = [(control, entry.amount, 0, memo), (old, 0, entry.amount, memo)]
        else:
            lines = [(old, entry.amount, 0, memo), (control, 0, entry.amount, memo)]
        journal = post_journal(
            date=business_date(), memo=memo[:255], source=JournalEntry.Source.MANUAL, reference=invoice.number,
            created_by=actor, lines=lines,
        )  # fmt: skip
        InvoicePayment.objects.create(
            invoice=invoice, entry=entry, amount=entry.amount, previous_category=old, journal=journal, created_by=actor
        )
        entry.category = control
        entry.save(update_fields=["category"])
        invoice.paid_amount += entry.amount
        invoice.status = Status.PAID if invoice.paid_amount == invoice.amount else Status.PART_PAID
        invoice.save(update_fields=["paid_amount", "status"])
        record(
            f"books.{invoice.kind.lower()}_paid", actor=actor, organization_id=invoice.organization_id, target=invoice,
            metadata={"number": invoice.number, "entry": entry.reference, "amount": str(entry.amount),
                      "outstanding": str(invoice.outstanding)},
        )  # fmt: skip
    return invoice


def cancel(*, invoice: Invoice, actor, reason: str) -> Invoice:
    """Cancels a bill or invoice recorded in error, reversing its journal. Only before anything is paid on it."""
    reason = reason.strip()
    if len(reason) < 5:
        raise BusinessError("Say why it's cancelled (at least 5 characters).", "reason_required")
    with db_transaction.atomic():
        invoice = Invoice.objects.select_for_update().select_related("journal").get(pk=invoice.pk)
        if invoice.status == Status.CANCELLED:
            return invoice
        if invoice.paid_amount > 0:
            raise BusinessError(
                f"{invoice.number} has payments linked to it, so it can't be cancelled.", "invoice_has_payments"
            )
        memo = f"Cancelled {invoice.number}: {reason}"
        lines = [(line.account, line.credit, line.debit, memo) for line in invoice.journal.lines.select_related("account")]
        post_journal(
            date=business_date(), memo=memo[:255], source=JournalEntry.Source.MANUAL, reference=invoice.number,
            created_by=actor, lines=lines, reverses=invoice.journal,
        )  # fmt: skip
        invoice.status, invoice.cancelled_by, invoice.cancelled_at = Status.CANCELLED, actor, timezone.now()
        invoice.save(update_fields=["status", "cancelled_by", "cancelled_at"])
        record(
            f"books.{invoice.kind.lower()}_cancelled", actor=actor, organization_id=invoice.organization_id,
            target=invoice, metadata={"number": invoice.number, "reason": reason[:200]},
        )  # fmt: skip
    return invoice


def totals(organization, currency: str) -> dict:
    """What's still owed each way, and how much of it is overdue."""
    today = business_date()
    result = {"payable": Decimal("0.00"), "receivable": Decimal("0.00"),
              "payable_overdue": Decimal("0.00"), "receivable_overdue": Decimal("0.00")}  # fmt: skip
    open_items = Invoice.objects.filter(
        organization=organization, currency=currency, status__in=(Status.OPEN, Status.PART_PAID)
    )
    for invoice in open_items:
        side = "payable" if invoice.kind == Kind.BILL else "receivable"
        result[side] += invoice.outstanding
        if invoice.due_date and invoice.due_date < today:
            result[f"{side}_overdue"] += invoice.outstanding
    return result
