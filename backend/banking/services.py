"""Money movement. Every balance change goes through here, inside a DB transaction."""
import secrets
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction as db_transaction
from rest_framework import status

from accounting import business as business_books
from accounting import services as books
from audit.services import record
from fluxpay.exceptions import BusinessError
from platform_settings import services as rules

from .models import Account, ManualAdjustment, Transaction, Transfer
from .signals import adjustment_posted, transfer_completed


def new_reference() -> str:
    return "FP" + secrets.token_hex(6).upper()


SYSTEM_USER_EMAIL = "system@fluxpay.internal"
BOOKED_BY_CALLER = "booked-by-caller"
AUDIT_ACTIONS = {"CREDIT": "adjustment.credited", "DEBIT": "adjustment.debited", "PAYOUT": "adjustment.paid_out"}


@db_transaction.atomic
def open_wallet(user, currency: str | None = None, name: str = "Main Wallet") -> Account:
    """Opens a personal wallet in an enabled currency (the platform default if none is given).

    If staff set a signup bonus for that currency, it is moved in from the Promotions system account,
    so the ledger still balances: no money is created.
    """
    code = rules.currency(currency or rules.platform().default_currency_id).code
    account = Account.objects.create(owner=user, currency=code, name=name)
    bonus = rules.currency(code).signup_bonus
    if bonus > 0:
        promotions = system_account(f"promotions:{code}", f"Promotions {code}", code)
        locked = {a.id: a for a in Account.objects.select_for_update().filter(id__in=[account.id, promotions.id])}
        account, promotions = locked[account.id], locked[promotions.id]
        reference = new_reference()
        promotions.balance -= bonus
        account.balance += bonus
        promotions.save(update_fields=["balance", "updated_at"])
        account.save(update_fields=["balance", "updated_at"])
        for line_account, side, counterparty in (
            (promotions, Transaction.Type.DEBIT, user.full_name),
            (account, Transaction.Type.CREDIT, "FluxPay"),
        ):
            Transaction.objects.create(
                account=line_account,
                type=side,
                category=Transaction.Category.BONUS,
                amount=bonus,
                balance_after=line_account.balance,
                counterparty_name=counterparty,
                description="Welcome bonus",
                reference=reference,
            )
        books.book_wallet_movement(
            role="promotions",
            currency=code,
            amount=bonus,
            into_wallets=True,
            memo=f"Welcome bonus for wallet {account.account_number}",
            reference=reference,
        )
    return account


def post_adjustment(*, staff, account_id, kind: str, amount: Decimal, reason: str, cashbook_entry) -> ManualAdjustment:
    """Moves money between a customer or business wallet and FluxPay's bank, through the cashbook.

    - CREDIT (top-up): credits the wallet from a customer deposit receipt, never more than is left on it.
    - DEBIT (correction): returns money from the wallet to the receipt it was credited from.
    - PAYOUT: the wallet side of a cash withdrawal; called by accounting.services.record_cashbook_entry.

    Each is booked in the general ledger. The currency's per-transaction limits apply (a guard against
    typing an extra zero), and a wallet can never go below zero. Permission is checked by the caller.
    """
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise BusinessError("Give a reason of at least 10 characters for the audit trail.", "reason_required")
    if cashbook_entry is None:
        raise BusinessError("Choose the bank receipt the money comes from.", "receipt_required")
    target = Account.objects.filter(id=account_id, system_key__isnull=True).first()
    if target is None:
        raise BusinessError("Customer wallet not found.", "account_not_found", status.HTTP_404_NOT_FOUND)
    if not target.is_active:
        raise BusinessError("This wallet is closed.", "account_inactive")
    rules.check_amount(amount, target.currency)
    credit = kind == ManualAdjustment.Kind.CREDIT
    if kind == ManualAdjustment.Kind.PAYOUT:
        pool = system_account(f"cashbook:{target.currency}", f"Bank payouts {target.currency}", target.currency)
    else:
        pool = system_account(
            f"adjustments:{target.currency}", f"Manual adjustments {target.currency}", target.currency
        )

    with db_transaction.atomic():
        # The receipt is locked before the wallets, so two staff can't allocate the same money twice.
        entry = books.lock_entry(cashbook_entry.pk)
        rows = Account.objects.select_for_update().filter(id__in=[target.id, pool.id]).order_by("id")
        locked = {a.id: a for a in rows}
        target, pool = locked[target.id], locked[pool.id]
        if not credit and target.balance < amount:
            raise BusinessError(
                f"The wallet only holds {target.balance:,.2f} {target.currency}; it can't go below zero.",
                "insufficient_funds",
            )
        if kind != ManualAdjustment.Kind.PAYOUT:
            problem = books.allocation_problem(entry, kind=kind, amount=amount, wallet=target, staff=staff)
            if problem:
                raise BusinessError(problem, "receipt_unavailable")
        source, destination = (pool, target) if credit else (target, pool)
        source.balance -= amount
        destination.balance += amount
        source.save(update_fields=["balance", "updated_at"])
        destination.save(update_fields=["balance", "updated_at"])

        reference = new_reference()
        description, category = {
            ManualAdjustment.Kind.CREDIT: ("Top-up by FluxPay", Transaction.Category.ADJUSTMENT),
            ManualAdjustment.Kind.DEBIT: ("Correction by FluxPay", Transaction.Category.ADJUSTMENT),
            ManualAdjustment.Kind.PAYOUT: ("Cash withdrawal paid by FluxPay", Transaction.Category.WITHDRAWAL),
        }[kind]
        for line_account, side in ((source, Transaction.Type.DEBIT), (destination, Transaction.Type.CREDIT)):
            on_wallet = line_account.id == target.id
            Transaction.objects.create(
                account=line_account,
                type=side,
                category=category,
                amount=amount,
                balance_after=line_account.balance,
                counterparty_name="FluxPay" if on_wallet else holder_name(target),
                counterparty_account="" if on_wallet else target.account_number,
                description=description,
                reference=reference,
            )
        adjustment = ManualAdjustment.objects.create(
            account=target,
            kind=kind,
            amount=amount,
            reason=reason,
            reference=reference,
            balance_after=target.balance,
            created_by=staff,
            cashbook_entry=entry,
        )
        books.book_adjustment(adjustment, entry)
        if target.organization_id:
            business_books.on_adjustment(adjustment)
        record(
            AUDIT_ACTIONS[kind],
            actor=staff,
            organization_id=target.organization_id,
            target=adjustment,
            metadata={
                "account": target.account_number,
                "amount": str(amount),
                "currency": target.currency,
                "reason": reason,
                "reference": reference,
                "cashbook_entry": entry.number,
            },
        )
        adjustment_posted.send(sender=ManualAdjustment, adjustment=adjustment)
    return adjustment


def system_account(key: str, name: str, currency: str) -> Account:
    """One of FluxPay's own accounts (clearing, promotions). Allowed to go negative. Created on first use."""
    account = Account.objects.filter(system_key=key).first()
    if account is not None:
        return account
    owner = _system_user()
    try:
        with db_transaction.atomic():
            return Account.objects.create(owner=owner, system_key=key, currency=currency, name=name)
    except IntegrityError:
        return Account.objects.get(system_key=key)


def _system_user():
    User = get_user_model()
    user = User.objects.filter(email=SYSTEM_USER_EMAIL).first()
    if user is not None:
        return user
    try:
        with db_transaction.atomic():
            # No usable password and inactive: this user can never log in.
            return User.objects.create_user(SYSTEM_USER_EMAIL, None, full_name="FluxPay", is_active=False)
    except IntegrityError:
        return User.objects.get(email=SYSTEM_USER_EMAIL)


def transfer_funds(*, user, source_id, destination_number: str, amount: Decimal, note: str, idempotency_key: str):
    """Moves money from one of the user's personal wallets. Returns (transfer, debit_transaction, created)."""
    return _transfer(
        initiator=user,
        may_spend=lambda source: source.owner_id == user.id and source.organization_id is None,
        source_id=source_id,
        destination_number=destination_number,
        amount=amount,
        note=note,
        idempotency_key=idempotency_key,
    )


def transfer_from_organization(*, initiator, organization, source_id, destination_number: str, amount: Decimal,
                               note: str, idempotency_key: str, books_role: str | None = None,
                               reference: str | None = None):
    """Moves money from a business wallet. The caller (organizations.services) has already checked the
    member's permission and any approval; this only confirms the wallet belongs to the organization.

    `books_role` files the payment in the business's books ("suppliers", "salaries", ...); BOOKED_BY_CALLER
    means the caller books it itself (payroll books each payslip as a payroll line) and the sender isn't
    alerted. `reference` is the business payment's own, so both share it."""
    return _transfer(
        books_role=books_role,
        reference=reference,
        initiator=initiator,
        may_spend=lambda source: source.organization_id == organization.id,
        source_id=source_id,
        destination_number=destination_number,
        amount=amount,
        note=note,
        idempotency_key=idempotency_key,
    )


def holder_name(account: Account) -> str:
    """The name shown to the other side of a transfer: the business for business wallets."""
    return account.organization.name if account.organization_id else account.owner.full_name


def _transfer(*, initiator, may_spend, source_id, destination_number: str, amount: Decimal, note: str,
              idempotency_key: str, books_role: str | None = None, reference: str | None = None):
    existing = Transfer.objects.filter(initiated_by=initiator, idempotency_key=idempotency_key).first()
    if existing:
        return existing, _debit_for(existing), False

    try:
        with db_transaction.atomic():
            # Lock both rows in a fixed order (by primary key) so two opposite transfers can't deadlock.
            destination_ref = Account.objects.filter(
                account_number=destination_number, is_active=True, system_key__isnull=True
            ).first()
            if destination_ref is None:
                raise BusinessError("No active account with that number.", "recipient_not_found", status.HTTP_404_NOT_FOUND)
            ids = sorted({str(source_id), str(destination_ref.id)})
            locked = {str(a.id): a for a in Account.objects.select_for_update().filter(id__in=ids).order_by("id")}

            source = locked.get(str(source_id))
            destination = locked[str(destination_ref.id)]
            if source is None or not source.is_active or not may_spend(source):
                raise BusinessError("Source account not found.", "account_not_found", status.HTTP_404_NOT_FOUND)
            if source.id == destination.id:
                raise BusinessError("You can't send money to the same account.", "same_account")
            rules.check_amount(amount, source.currency)
            if source.currency != destination.currency:
                raise BusinessError(
                    f"Currency mismatch: {source.currency} → {destination.currency}. Cross-currency transfers aren't supported yet.",
                    "currency_mismatch",
                )
            if source.balance < amount:
                raise BusinessError("Insufficient funds for this transfer.", "insufficient_funds")

            reference = reference or new_reference()
            source.balance -= amount
            destination.balance += amount
            source.save(update_fields=["balance", "updated_at"])
            destination.save(update_fields=["balance", "updated_at"])

            transfer = Transfer.objects.create(
                initiated_by=initiator,
                source=source,
                destination=destination,
                amount=amount,
                note=note,
                reference=reference,
                idempotency_key=idempotency_key,
            )
            debit = Transaction.objects.create(
                account=source,
                type=Transaction.Type.DEBIT,
                category=Transaction.Category.TRANSFER_OUT,
                amount=amount,
                balance_after=source.balance,
                counterparty_name=holder_name(destination),
                counterparty_account=destination.account_number,
                description=note or f"Sent to {holder_name(destination)}",
                reference=reference,
            )
            Transaction.objects.create(
                account=destination,
                type=Transaction.Type.CREDIT,
                category=Transaction.Category.TRANSFER_IN,
                amount=amount,
                balance_after=destination.balance,
                counterparty_name=holder_name(source),
                counterparty_account=source.account_number,
                description=note or f"Received from {holder_name(source)}",
                reference=reference,
            )
            if books_role != BOOKED_BY_CALLER and (source.organization_id or destination.organization_id):
                business_books.on_transfer(transfer, source, destination, out_role=books_role)
            # Accounts are locked above, before the audit log's lock (see audit.services).
            record(
                "transfer.created",
                actor=initiator,
                organization_id=source.organization_id,
                target=transfer,
                metadata={
                    "amount": str(amount),
                    "currency": source.currency,
                    "from": source.account_number,
                    "to": destination.account_number,
                    "reference": reference,
                },
            )
            transfer_completed.send(sender=Transfer, transfer=transfer, notify_sender=books_role != BOOKED_BY_CALLER)
            return transfer, debit, True
    except IntegrityError:
        # A concurrent request with the same idempotency key won the race.
        existing = Transfer.objects.get(initiated_by=initiator, idempotency_key=idempotency_key)
        return existing, _debit_for(existing), False


def reverse_transfer(
    *, transfer: Transfer, initiator, reason: str, books_role: str | None = None, book=None
) -> Transfer:
    """Takes a payment back from the person who received it (e.g. a salary paid to the wrong worker).

    Refused if the recipient no longer holds the money: it is never taken below zero. The caller checks
    that `initiator` may do this. Safe to call twice: a transfer is only ever reversed once.
    With books_role=BOOKED_BY_CALLER, `book(reversal)` is called to do the booking, before the audit lock.
    """
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise BusinessError("Say why the payment is being reversed.", "reason_required")
    with db_transaction.atomic():
        ids = sorted({str(transfer.source_id), str(transfer.destination_id)})
        locked = {str(a.id): a for a in Account.objects.select_for_update().filter(id__in=ids).order_by("id")}
        payer, payee = locked[str(transfer.source_id)], locked[str(transfer.destination_id)]
        if Transfer.objects.filter(reverses=transfer).exists():
            raise BusinessError("This payment has already been reversed.", "already_reversed")
        if payee.balance < transfer.amount:
            raise BusinessError(
                f"{holder_name(payee)} only has {payee.balance:,.2f} {payee.currency} left, so the "
                f"{transfer.amount:,.2f} can't be taken back. Ask them to send it back.",
                "insufficient_funds",
            )
        reference = new_reference()
        payee.balance -= transfer.amount
        payer.balance += transfer.amount
        payee.save(update_fields=["balance", "updated_at"])
        payer.save(update_fields=["balance", "updated_at"])
        reversal = Transfer.objects.create(
            initiated_by=initiator,
            source=payee,
            destination=payer,
            amount=transfer.amount,
            note=f"Reversal of {transfer.reference}: {reason}"[:140],
            reference=reference,
            idempotency_key=f"reversal-{transfer.id}",
            reverses=transfer,
        )
        for account, side, category, other, text in (
            (payee, Transaction.Type.DEBIT, Transaction.Category.TRANSFER_OUT, payer,
             f"Reversed by {holder_name(payer)}: {reason}"),
            (payer, Transaction.Type.CREDIT, Transaction.Category.TRANSFER_IN, payee,
             f"Reversal of payment to {holder_name(payee)}"),
        ):  # fmt: skip
            Transaction.objects.create(
                account=account,
                type=side,
                category=category,
                amount=transfer.amount,
                balance_after=account.balance,
                counterparty_name=holder_name(other),
                counterparty_account=other.account_number,
                description=text[:140],
                reference=reference,
            )
        if books_role == BOOKED_BY_CALLER:
            if book is not None:
                book(reversal)
        elif payer.organization_id or payee.organization_id:
            business_books.on_transfer(reversal, payee, payer, out_role=books_role)
        record(
            "transfer.reversed",
            actor=initiator,
            organization_id=payer.organization_id,
            target=reversal,
            metadata={
                "original": transfer.reference,
                "reference": reference,
                "amount": str(transfer.amount),
                "currency": payer.currency,
                "from": payee.account_number,
                "to": payer.account_number,
                "reason": reason,
            },
        )
        transfer_completed.send(sender=Transfer, transfer=reversal)
    return reversal


def _debit_for(transfer: Transfer) -> Transaction:
    return Transaction.objects.get(reference=transfer.reference, type=Transaction.Type.DEBIT)
