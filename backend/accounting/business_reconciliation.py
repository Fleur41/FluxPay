"""Does a business's money add up? One report checks its cashbook, its ledger, its payments and its outside payouts
against each other, and lists what doesn't match (problems) and what is still in flight (attention).

1. Balances: the cashbook wallet's balance = its ledger (every money movement on it, credits - debits) = its
   business cashbook (money in - money out).
2. References: every money movement has a cashbook line with the same reference and amount, and the other way
   round. Movements from before the business's books started are covered by the opening balance line; pay runs
   paid before each payslip had its own line are matched against their single run line.
3. Payments: a paid payment has its money movement; one still processing hasn't already been settled by M-Pesa or
   the bank; a reversed one has its reversal. Payments of the same amount to the same recipient minutes apart are
   listed as possible duplicates.
4. Outside payouts: anything M-Pesa or the bank hasn't settled, and anything held for staff review.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from banking.models import Account, Transaction

from .models import ZERO, BusinessEntry

CENT = Decimal("0.01")
DUPLICATE_WINDOW = timedelta(minutes=10)
PROCESSING_TOO_LONG = timedelta(hours=24)


def reconcile(organization) -> dict:
    from organizations.models import Payment
    from payments.models import ExternalPayment
    from payroll.models import PayRun

    wallet = Account.objects.filter(organization=organization).first()
    problems, attention = [], []
    if wallet is None:
        return {"balanced": False, "problems": [_item("no_cashbook", "This business has no cashbook.")], "attention": []}

    def money(amount) -> str:
        return f"{wallet.currency} {amount:,.2f}"

    # 1. Balances
    lines = Transaction.objects.filter(account=wallet)
    totals = lines.aggregate(
        credits=Sum("amount", filter=Q(type=Transaction.Type.CREDIT)),
        debits=Sum("amount", filter=Q(type=Transaction.Type.DEBIT)),
    )
    ledger = ((totals["credits"] or ZERO) - (totals["debits"] or ZERO)).quantize(CENT)
    entries = BusinessEntry.objects.filter(organization=organization, wallet=wallet)
    book_totals = entries.aggregate(
        money_in=Sum("amount", filter=Q(direction="IN")), money_out=Sum("amount", filter=Q(direction="OUT"))
    )
    cashbook = ((book_totals["money_in"] or ZERO) - (book_totals["money_out"] or ZERO)).quantize(CENT)
    if ledger != wallet.balance:
        problems.append(_item("ledger_mismatch",
                              f"The wallet holds {money(wallet.balance)} but its money movements add up to {money(ledger)}.",
                              amount=wallet.balance - ledger))  # fmt: skip
    if cashbook != wallet.balance:
        problems.append(_item("cashbook_mismatch",
                              f"The wallet holds {money(wallet.balance)} but the cashbook adds up to {money(cashbook)}.",
                              amount=wallet.balance - cashbook))  # fmt: skip

    # 2. References: movement vs cashbook line, net per reference
    # Businesses that already had money when business books were introduced got an opening balance line;
    # movements before it are summed up in it. For every other business, every movement must match.
    books_started = entries.filter(source=BusinessEntry.Source.OPENING).values_list("created_at", flat=True).first()
    legacy_runs = {
        run.book_entry.reference: run
        for run in PayRun.objects.filter(organization=organization, book_entry__isnull=False).select_related("book_entry")
    }
    alias = {  # a payslip of a run booked as one line -> that line's reference
        reference: run_reference
        for run_reference, run in legacy_runs.items()
        for reference in run.payslips.values_list("reference", flat=True)
    }
    moved = defaultdict(lambda: ZERO)
    for reference, kind, amount, created_at in lines.values_list("reference", "type", "amount", "created_at"):
        if books_started is not None and created_at < books_started:
            continue  # before the books: in the opening balance
        moved[alias.get(reference, reference)] += amount if kind == Transaction.Type.CREDIT else -amount
    booked = defaultdict(lambda: ZERO)
    for reference, direction, amount, source in entries.values_list("reference", "direction", "amount", "source"):
        if source == BusinessEntry.Source.OPENING:
            continue
        booked[reference] += amount if direction == "IN" else -amount
    for reference in sorted(set(moved) | set(booked)):
        if reference not in booked:
            problems.append(_item("not_in_cashbook", f"{money(moved[reference])} moved with no cashbook line.",
                                  reference=reference, amount=moved[reference]))  # fmt: skip
        elif reference not in moved:
            problems.append(_item("not_in_ledger", f"A cashbook line of {money(booked[reference])} with no money movement.",
                                  reference=reference, amount=booked[reference]))  # fmt: skip
        elif moved[reference] != booked[reference]:
            problems.append(_item("amounts_differ",
                                  f"{money(moved[reference])} moved but the cashbook says {money(booked[reference])}.",
                                  reference=reference, amount=moved[reference] - booked[reference]))  # fmt: skip

    # 3. Payments
    P = Payment.Status
    payments = Payment.objects.filter(organization=organization).select_related("external_payment", "transfer")
    now = timezone.now()
    for payment in payments:
        external = payment.external_payment
        label = f"{payment.get_type_display()} of {money(payment.amount)} to {payment.recipient_name}"
        if payment.status == P.COMPLETED and payment.transfer_id is None and (
            external is None or external.status != external.Status.COMPLETED
        ):
            problems.append(_item("paid_without_money", f"{label} is marked paid but no money moved.",
                                  reference=payment.reference, amount=payment.amount))  # fmt: skip
        elif payment.status == P.PROCESSING:
            settled = external is not None and external.status in (
                external.Status.COMPLETED, external.Status.REVERSED, external.Status.FAILED
            )
            if settled:
                problems.append(_item("status_out_of_step",
                                      f"{label} is still processing, but the payout is {external.get_status_display().lower()}.",
                                      reference=payment.reference, amount=payment.amount))  # fmt: skip
            else:
                waited = now - (external.created_at if external else payment.created_at)
                attention.append(_item("processing",
                                       f"{label} is waiting for {external.get_rail_display() if external else 'the provider'}"
                                       + (" for over a day." if waited > PROCESSING_TOO_LONG else "."),
                                       reference=payment.reference, amount=payment.amount))  # fmt: skip
        elif payment.status == P.REVERSED and payment.reversal_id is None:
            problems.append(_item("reversed_without_money", f"{label} is marked reversed but nothing came back.",
                                  reference=payment.reference, amount=payment.amount))  # fmt: skip
        elif payment.status == P.PENDING_APPROVAL:
            attention.append(_item("waiting_for_approval", f"{label} is waiting for approval.",
                                   reference=payment.reference, amount=payment.amount))  # fmt: skip

    # Same amount to the same recipient, minutes apart: probably paid twice.
    paid = defaultdict(list)
    for payment in payments:
        if payment.status == P.COMPLETED and payment.pay_run_id is None:
            paid[(payment.destination_account_number or payment.recipient_name, payment.amount)].append(payment)
    for (_recipient, amount), group in paid.items():
        group.sort(key=lambda p: p.created_at)
        for first, second in zip(group, group[1:]):
            if second.created_at - first.created_at <= DUPLICATE_WINDOW:
                attention.append(_item("possible_duplicate",
                                       f"{money(amount)} to {second.recipient_name} twice within minutes "
                                       f"({first.reference} and {second.reference}). Check it wasn't paid twice.",
                                       reference=second.reference, amount=amount))  # fmt: skip

    # 4. Outside payouts and deposits
    X = ExternalPayment.Status
    reported = {p.external_payment_id for p in payments if p.external_payment_id}  # already listed as payments
    unsettled = ExternalPayment.objects.filter(account=wallet).exclude(status__in=[X.COMPLETED, X.FAILED, X.EXPIRED, X.REVERSED])
    for external in unsettled.exclude(id__in=reported):
        attention.append(_item("payout_unsettled" if external.direction == "OUT" else "deposit_unsettled",
                               f"{external.get_method_display()} of {money(external.amount)} is {external.get_status_display().lower()}.",
                               reference=external.reference, amount=external.amount))  # fmt: skip
    for external in ExternalPayment.objects.filter(account=wallet, needs_review=True):
        problems.append(_item("needs_review", f"{external.get_method_display()} of {money(external.amount)} is held for "
                                              f"FluxPay staff to check: {external.review_note}",
                              reference=external.reference, amount=external.amount))  # fmt: skip

    return {
        "as_at": now,
        "currency": wallet.currency,
        "account_number": wallet.account_number,
        "balances": {"wallet": str(wallet.balance), "ledger": str(ledger), "cashbook": str(cashbook)},
        "balanced": not problems,
        "problems": problems,
        "attention": attention,
        "checked": {"movements": lines.count(), "cashbook_lines": entries.count(), "payments": len(payments)},
    }


def _item(kind: str, message: str, *, reference: str = "", amount: Decimal | None = None) -> dict:
    return {"kind": kind, "message": message, "reference": reference, "amount": str(amount) if amount is not None else None}
