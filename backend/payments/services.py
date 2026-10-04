"""External money movement. Every status change and ledger line for an external payment goes through here.

Rules (see the design doc, "Payment states and money-safety rules"):
- A wallet only changes when a deposit completes, a withdrawal is held, or a held withdrawal is returned.
- Every transition locks the payment row and checks its current status, so a callback and a status
  check racing each other settle a payment once.
- A callback never settles a payment by itself; the outcome always comes from the provider's status API.
- An unclear answer (ProviderState.UNKNOWN, ProviderUnavailable) never fails or reverses a payment.

Business cashbooks use the same paths (organizations.services calls `deposit_into` and `hold_payout`), and
each movement on one is also written in that business's own books.

Lock order is always: payment row, then account rows by primary key. Keep it that way to avoid deadlocks.
"""
import logging
from decimal import Decimal

from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import status

from accounting import business as business_books
from accounting import services as books
from accounting.models import BusinessEntry, CashbookEntry
from audit.services import record
from banking.models import Account, Transaction
from banking.services import holder_name, new_reference, system_account
from fluxpay.exceptions import BusinessError
from platform_settings import services as rules

from .models import ExternalPayment, WebhookEvent, rail_label
from .providers import get_provider
from .providers.base import ProviderError, ProviderState, StatusResult
from .signals import payment_settled

logger = logging.getLogger(__name__)

Status = ExternalPayment.Status
Direction = ExternalPayment.Direction

# Statuses from which each outcome may be applied.
COMPLETABLE = {
    Direction.IN: {Status.CREATED, Status.PENDING, Status.EXPIRED},
    Direction.OUT: {Status.HELD, Status.SUBMITTED},
}
FAILABLE = {
    Direction.IN: {Status.CREATED, Status.PENDING},
    Direction.OUT: {Status.HELD, Status.SUBMITTED},
}
SUBMITTABLE = {Direction.IN: Status.CREATED, Direction.OUT: Status.HELD}
AFTER_SUBMIT = {Direction.IN: Status.PENDING, Direction.OUT: Status.SUBMITTED}


class PaymentNotFound(Exception):
    """A callback names a provider reference we have not recorded (yet)."""


# --- Clearing accounts -------------------------------------------------------------------------


def clearing_account(rail: str, currency: str) -> Account:
    """FluxPay's account mirroring the money held at one provider in one currency. Created on first use."""
    return system_account(f"clearing:{rail}:{currency}", f"{rail_label(rail)} clearing {currency}", currency)


# --- Starting payments -------------------------------------------------------------------------


def start_deposit(*, user, account_id, rail: str, method: str, amount: Decimal, idempotency_key: str, metadata=None):
    """Records a deposit into one of the user's own wallets and queues it. Returns (payment, created)."""
    existing = _existing(user, idempotency_key)
    if existing:
        return existing, False
    _require_provider(rail)
    account = _personal_wallet(user, account_id)
    if account is None:
        raise BusinessError("Account not found.", "account_not_found", status.HTTP_404_NOT_FOUND)
    return deposit_into(account, initiator=user, rail=rail, method=method, amount=amount,
                        idempotency_key=idempotency_key, metadata=metadata)  # fmt: skip


def deposit_into(account: Account, *, initiator, rail: str, method: str, amount: Decimal, idempotency_key: str,
                 metadata=None):  # fmt: skip
    """Records a deposit into `account` (permission already checked) and queues its submission to the provider."""
    existing = _existing(initiator, idempotency_key)
    if existing:
        return existing, False
    check_payable_amount(rail, amount, account.currency)
    try:
        with db_transaction.atomic():
            payment = ExternalPayment.objects.create(
                account=account,
                initiated_by=initiator,
                direction=Direction.IN,
                rail=rail,
                method=method,
                status=Status.CREATED,
                amount=amount,
                currency=account.currency,
                reference=new_reference(),
                idempotency_key=idempotency_key,
                metadata=metadata or {},
            )
            _audit("payment.deposit_started", payment, actor=initiator)
            _queue_submit(payment)
    except IntegrityError:
        return ExternalPayment.objects.get(initiated_by=initiator, idempotency_key=idempotency_key), False
    return payment, True


def start_payout(*, user, account_id, rail: str, method: str, amount: Decimal, idempotency_key: str, metadata=None):
    """Takes the money out of one of the user's own wallets (HELD) and queues the payout. Returns (payment, created)."""
    existing = _existing(user, idempotency_key)
    if existing:
        return existing, False
    _require_provider(rail)
    wallet = _personal_wallet(user, account_id)
    if wallet is None:
        raise BusinessError("Account not found.", "account_not_found", status.HTTP_404_NOT_FOUND)
    try:
        with db_transaction.atomic():
            return hold_payout(wallet, initiator=user, rail=rail, method=method, amount=amount,
                               idempotency_key=idempotency_key, metadata=metadata), True  # fmt: skip
    except IntegrityError:
        return ExternalPayment.objects.get(initiated_by=user, idempotency_key=idempotency_key), False


def hold_payout(wallet: Account, *, initiator, rail: str, method: str, amount: Decimal, idempotency_key: str,
                metadata=None, reference: str | None = None) -> ExternalPayment:  # fmt: skip
    """Moves `amount` out of `wallet` into the rail's clearing account and queues the payout. Call inside a
    transaction; the caller has checked who may spend from the wallet.

    For a business cashbook, `metadata["books_role"]` files the payout in the business's books and
    `metadata["description"]` is what its cashbook and the wallet's history show. `reference` lets a business
    payment and its payout share one reference.
    """
    check_payable_amount(rail, amount, wallet.currency)
    if not get_provider(rail).can_pay_out():
        raise BusinessError(f"Payouts by {rail_label(rail)} aren't available yet.", "rail_unavailable")
    clearing = clearing_account(rail, wallet.currency)
    locked = _lock_accounts(wallet.id, clearing.id)
    wallet, clearing = locked[wallet.id], locked[clearing.id]
    if wallet.balance < amount:
        raise BusinessError("Insufficient funds for this withdrawal.", "insufficient_funds")
    payment = ExternalPayment.objects.create(
        account=wallet,
        initiated_by=initiator,
        direction=Direction.OUT,
        rail=rail,
        method=method,
        status=Status.HELD,
        amount=amount,
        currency=wallet.currency,
        reference=reference or new_reference(),
        idempotency_key=idempotency_key,
        metadata=metadata or {},
    )
    _post(
        payment,
        debit=wallet,
        credit=clearing,
        debit_category=Transaction.Category.WITHDRAWAL,
        credit_category=Transaction.Category.WITHDRAWAL,
        line_status=Transaction.Status.PENDING,
    )
    _audit("payment.payout_started", payment, actor=initiator)
    _queue_submit(payment)
    return payment


def check_payable_amount(rail: str, amount: Decimal, currency: str) -> None:
    """The rail is on, settles in `currency`, takes this amount, and the platform's limits allow it."""
    _require_provider(rail)
    _require_currency(rail, currency)
    if get_provider(rail).whole_units_only and amount != amount.to_integral_value():
        raise BusinessError(f"{rail_label(rail)} amounts must be whole {currency}, without cents.", "whole_amount_only")
    rules.check_amount(amount, currency)


def submit_payment(payment_id) -> ExternalPayment:
    """Sends a CREATED deposit or HELD payout to its provider. Safe to call again (payouts are idempotent).

    ProviderUnavailable propagates so the caller (a Celery task) retries; the payment keeps its status.
    """
    payment = ExternalPayment.objects.get(id=payment_id)
    if payment.status != SUBMITTABLE[payment.direction]:
        return payment
    provider = get_provider(payment.rail)
    if payment.direction == Direction.OUT and not provider.payouts_idempotent:
        # Sending it again could pay twice: record the attempt first, and never make a second one.
        with db_transaction.atomic():
            payment = _lock_payment(payment_id)
            if payment.status != Status.HELD:
                return payment
            if payment.metadata.get("submit_attempted"):
                _flag(payment, "The first attempt to send this payout got no answer. Check with the provider "
                               "before confirming or failing it; it won't be sent again automatically.")
                return payment
            payment.metadata = {**payment.metadata, "submit_attempted": timezone.now().isoformat()}
            payment.save(update_fields=["metadata", "updated_at"])
    try:
        if payment.direction == Direction.IN:
            result = provider.start_deposit(payment)
        else:
            result = provider.start_payout(payment)
    except ProviderError as exc:
        return fail_payment(payment.id, str(exc))

    with db_transaction.atomic():
        payment = _lock_payment(payment_id)
        if payment.status != SUBMITTABLE[payment.direction]:
            return payment
        payment.provider_ref = result.provider_ref
        payment.metadata = {**payment.metadata, **result.metadata}
        payment.status = AFTER_SUBMIT[payment.direction]
        payment.save(update_fields=["provider_ref", "metadata", "status", "updated_at"])
    return payment


# --- Settling payments -------------------------------------------------------------------------


def settle_from_status(payment_id, result: StatusResult) -> ExternalPayment:
    """Applies what the provider's status API reported. PENDING and UNKNOWN leave the payment as it is."""
    if result.state == ProviderState.SUCCEEDED:
        return complete_payment(payment_id, result)
    if result.state == ProviderState.FAILED:
        return fail_payment(payment_id, result.reason or "Rejected by the provider")
    return ExternalPayment.objects.get(id=payment_id)


def complete_payment(payment_id, result: StatusResult) -> ExternalPayment:
    """Deposit: credits the wallet. Withdrawal: marks the held lines completed. Applied at most once."""
    with db_transaction.atomic():
        payment = _lock_payment(payment_id)
        if payment.status not in COMPLETABLE[payment.direction]:
            if payment.status == Status.FAILED:
                _flag(payment, "Provider reported success after reporting failure.")
            return payment
        if result.amount is not None and (result.amount != payment.amount or result.currency != payment.currency):
            _flag(
                payment,
                f"Provider reported {result.amount} {result.currency}, expected {payment.amount} {payment.currency}.",
            )
            return payment

        if payment.direction == Direction.IN:
            clearing = clearing_account(payment.rail, payment.currency)
            locked = _lock_accounts(payment.account_id, clearing.id)
            _post(
                payment,
                debit=locked[clearing.id],
                credit=locked[payment.account_id],
                debit_category=Transaction.Category.DEPOSIT,
                credit_category=Transaction.Category.DEPOSIT,
                line_status=Transaction.Status.COMPLETED,
            )
            if payment.account.organization_id:  # money paid in by the owners, until they re-file it
                business_books.record_movement(
                    wallet=payment.account, direction="IN", amount=payment.amount,
                    source=BusinessEntry.Source.PROVIDER_DEPOSIT, reference=payment.reference,
                    counterparty=payment.metadata.get("phone_number", "") or rail_label(payment.rail),
                    description=f"Deposit by {rail_label(payment.rail)}", role="capital",
                    actor=payment.initiated_by,
                )  # fmt: skip
        else:
            Transaction.objects.filter(reference=payment.reference, status=Transaction.Status.PENDING).update(
                status=Transaction.Status.COMPLETED
            )

        payment.status = Status.COMPLETED
        payment.completed_at = timezone.now()
        if result.provider_ref and not payment.provider_ref:
            payment.provider_ref = result.provider_ref
        payment.save(update_fields=["status", "completed_at", "provider_ref", "updated_at"])
        _audit("payment.completed", payment)
        payment_settled.send(sender=ExternalPayment, payment=payment)
    return payment


def fail_payment(payment_id, reason: str) -> ExternalPayment:
    """Deposit: marks it FAILED (no money moved). Withdrawal: returns the held money and marks it REVERSED.

    Only call this on a definite failure from the provider, never on a timeout.
    """
    with db_transaction.atomic():
        payment = _lock_payment(payment_id)
        if payment.status not in FAILABLE[payment.direction]:
            return payment

        if payment.direction == Direction.IN:
            payment.status = Status.FAILED
        else:
            clearing = clearing_account(payment.rail, payment.currency)
            locked = _lock_accounts(payment.account_id, clearing.id)
            Transaction.objects.filter(reference=payment.reference, status=Transaction.Status.PENDING).update(
                status=Transaction.Status.FAILED
            )
            _post(
                payment,
                debit=locked[clearing.id],
                credit=locked[payment.account_id],
                debit_category=Transaction.Category.WITHDRAWAL_REVERSAL,
                credit_category=Transaction.Category.WITHDRAWAL_REVERSAL,
                line_status=Transaction.Status.COMPLETED,
            )
            if payment.account.organization_id:  # back under the category the payout was filed in
                sent = BusinessEntry.objects.filter(
                    wallet_id=payment.account_id, reference=payment.reference, direction="OUT"
                ).select_related("category").first()
                business_books.record_movement(
                    wallet=payment.account, direction="IN", amount=payment.amount,
                    source=BusinessEntry.Source.PAYOUT_RETURNED, reference=payment.reference,
                    counterparty=rail_label(payment.rail), description=f"Returned: {reason}"[:255],
                    category_account=sent.category if sent else None, role=None if sent else "drawings",
                )  # fmt: skip
            payment.status = Status.REVERSED
        payment.failure_reason = reason[:255]
        payment.save(update_fields=["status", "failure_reason", "updated_at"])
        _audit("payment.reversed" if payment.status == Status.REVERSED else "payment.failed", payment)
        payment_settled.send(sender=ExternalPayment, payment=payment)
    return payment


def expire_payment(payment_id) -> ExternalPayment:
    """Stops waiting on a deposit the user never approved. A late success can still complete it."""
    with db_transaction.atomic():
        payment = _lock_payment(payment_id)
        if payment.direction != Direction.IN or payment.status not in (Status.CREATED, Status.PENDING):
            return payment
        payment.status = Status.EXPIRED
        payment.save(update_fields=["status", "updated_at"])
    return payment


def expire_if_abandoned(payment_id) -> ExternalPayment:
    """For an old deposit: settles it if the provider has an outcome, expires it if still pending.

    UNKNOWN leaves it alone; the next run asks again. A deposit that never got a provider reference
    has nothing to ask about, so it expires straight away.
    """
    payment = ExternalPayment.objects.get(id=payment_id)
    if payment.status == Status.CREATED and not payment.provider_ref:
        return expire_payment(payment.id)
    result = get_provider(payment.rail).fetch_status(payment)
    if result.state == ProviderState.PENDING:
        return expire_payment(payment.id)
    return settle_from_status(payment.id, result)


def check_with_provider(payment_id) -> ExternalPayment:
    """Asks the provider for the payment's outcome and applies it. ProviderUnavailable propagates."""
    payment = ExternalPayment.objects.get(id=payment_id)
    result = get_provider(payment.rail).fetch_status(payment)
    return settle_from_status(payment.id, result)


# --- Staff ----------------------------------------------------------------------------------------


def confirm_bank_payout(*, staff, payment_id, bank, bank_reference: str, date) -> ExternalPayment:
    """Staff sent a queued bank payout from FluxPay's bank `bank`: records the payment in FluxPay's cashbook
    (Dr bank clearing, Cr bank) and completes the payout."""
    bank_reference = (bank_reference or "").strip()
    if not bank_reference:
        raise BusinessError("Enter the bank's reference for the transfer.", "bank_reference_required")
    with db_transaction.atomic():
        payment = _lock_payment(payment_id)
        if payment.rail != "BANK" or payment.direction != Direction.OUT or payment.status not in COMPLETABLE[Direction.OUT]:
            raise BusinessError("Only a bank payout waiting for staff can be confirmed.", "not_waiting")
        if bank.currency != payment.currency:
            raise BusinessError(f"Choose a {payment.currency} bank account.", "currency_mismatch")
        meta = payment.metadata
        entry = books.record_cashbook_entry(
            staff=staff, bank=bank, category=CashbookEntry.Category.BANK_PAYOUT, amount=payment.amount, date=date,
            counterparty=meta.get("bank_account_name") or holder_name(payment.account),
            description=f"Payout {payment.reference} from wallet {payment.account.account_number}",
            bank_reference=bank_reference,
        )  # fmt: skip
        payment.metadata = {**meta, "staff_outcome": "sent", "bank_reference": bank_reference,
                            "cashbook_entry": entry.number, "confirmed_by": staff.email}  # fmt: skip
        payment.save(update_fields=["metadata", "updated_at"])
        payment = complete_payment(payment.id, StatusResult(state=ProviderState.SUCCEEDED))
    return payment


def staff_complete_payout(*, staff, payment_id, receipt: str, note: str) -> ExternalPayment:
    """Staff checked with the provider (e.g. the M-Pesa portal) that a payout with no result did go through."""
    receipt, note = (receipt or "").strip(), (note or "").strip()
    if not receipt or len(note) < 10:
        raise BusinessError("Enter the provider's receipt and how you checked it (10 characters or more).", "note_required")
    with db_transaction.atomic():
        payment = _lock_payment(payment_id)
        if payment.direction != Direction.OUT or payment.status not in COMPLETABLE[Direction.OUT] or payment.rail == "BANK":
            raise BusinessError("Only an unsettled M-Pesa payout can be confirmed here.", "not_waiting")
        payment.metadata = {**payment.metadata, "staff_outcome": "sent", "staff_note": note,
                            "provider_receipt": receipt, "confirmed_by": staff.email}  # fmt: skip
        payment.needs_review, payment.review_note = False, ""
        payment.save(update_fields=["metadata", "needs_review", "review_note", "updated_at"])
        record("payment.staff_confirmed", actor=staff, target=payment,
               metadata={"reference": payment.reference, "receipt": receipt, "note": note})  # fmt: skip
        payment = complete_payment(payment.id, StatusResult(state=ProviderState.SUCCEEDED))
    return payment


def staff_fail_payout(*, staff, payment_id, reason: str) -> ExternalPayment:
    """Staff found a payout was not paid (a bank transfer that bounced, or an M-Pesa payout the provider never
    made): the money goes back to the wallet."""
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise BusinessError("Say why the payout failed (10 characters or more).", "reason_required")
    with db_transaction.atomic():
        payment = _lock_payment(payment_id)
        if payment.direction != Direction.OUT or payment.status not in FAILABLE[Direction.OUT]:
            raise BusinessError("Only an unsettled payout can be failed.", "not_waiting")
        payment.metadata = {**payment.metadata, "staff_outcome": "failed", "staff_note": reason,
                            "confirmed_by": staff.email}  # fmt: skip
        payment.needs_review, payment.review_note = False, ""
        payment.save(update_fields=["metadata", "needs_review", "review_note", "updated_at"])
        record("payment.staff_failed", actor=staff, target=payment,
               metadata={"reference": payment.reference, "reason": reason})  # fmt: skip
        payment = fail_payment(payment.id, reason)
    return payment


def flag_silent_payouts(older_than) -> int:
    """Flags submitted payouts with no outcome since `older_than` for staff. Bank payouts wait for staff anyway."""
    silent = ExternalPayment.objects.filter(
        direction=Direction.OUT, status=Status.SUBMITTED, needs_review=False, updated_at__lt=older_than
    ).exclude(rail="BANK")
    return silent.update(
        needs_review=True,
        review_note="No outcome from the provider yet. Check its portal, then confirm or fail the payout.",
        updated_at=timezone.now(),
    )


# --- Webhooks ----------------------------------------------------------------------------------


def record_webhook(rail: str, headers: dict, payload: dict) -> WebhookEvent | None:
    """Validates and stores a callback, then queues it. Returns None for a replay we already have.

    Raises InvalidCallback (from the provider) for a callback that fails its checks.
    """
    callback = get_provider(rail).parse_callback(headers, payload)
    try:
        with db_transaction.atomic():
            event = WebhookEvent.objects.create(rail=rail, event_id=callback.event_id, headers=headers, payload=payload)
            from .tasks import process_webhook_event

            db_transaction.on_commit(lambda: process_webhook_event.delay(str(event.id)), robust=True)
    except IntegrityError:
        return None
    return event


def process_webhook(event_id) -> WebhookEvent:
    """Settles the payment a stored callback is about, using the provider's status API.

    Raises PaymentNotFound when the payment's provider reference is not recorded yet (the callback can
    beat the submit response); the task retries, and gives up through `give_up_on_webhook`.
    """
    event = WebhookEvent.objects.get(id=event_id)
    if event.processed_at is not None:
        return event
    provider = get_provider(event.rail)
    callback = provider.parse_callback(event.headers, event.payload)
    payment = ExternalPayment.objects.filter(rail=event.rail, provider_ref=callback.provider_ref).first()
    if payment is None:
        raise PaymentNotFound(callback.provider_ref)

    if callback.details:
        with db_transaction.atomic():
            locked = _lock_payment(payment.id)
            locked.metadata = {**locked.metadata, **callback.details}
            locked.save(update_fields=["metadata", "updated_at"])
        payment.refresh_from_db()  # the provider may read the outcome from these details (M-Pesa payouts)
    settle_from_status(payment.id, provider.fetch_status(payment))
    event.payment = payment
    event.processed_at = timezone.now()
    event.save(update_fields=["payment", "processed_at"])
    return event


def give_up_on_webhook(event_id, error: str) -> None:
    WebhookEvent.objects.filter(id=event_id, processed_at__isnull=True).update(
        processed_at=timezone.now(), error=error[:2000]
    )


# --- Helpers -----------------------------------------------------------------------------------


def _personal_wallet(user, account_id):
    """The user's own active wallet. Business wallets are excluded: they move money through organizations."""
    return Account.objects.filter(
        id=account_id, owner=user, organization__isnull=True, is_active=True, system_key__isnull=True
    ).first()


def _existing(user, idempotency_key: str):
    return ExternalPayment.objects.filter(initiated_by=user, idempotency_key=idempotency_key).first()


def _require_provider(rail: str) -> None:
    try:
        get_provider(rail)
    except LookupError:
        raise BusinessError("This payment method isn't available.", "rail_unavailable") from None


def _require_currency(rail: str, currency: str) -> None:
    """The provider adapter declares which currencies it settles in (None: any)."""
    allowed = get_provider(rail).currencies
    if allowed is not None and currency not in allowed:
        raise BusinessError(
            f"{rail_label(rail)} works with {', '.join(sorted(allowed))} wallets, not {currency}.",
            "currency_not_supported",
        )


def _queue_submit(payment: ExternalPayment) -> None:
    from .tasks import submit_payment_task

    payment_id = str(payment.id)
    db_transaction.on_commit(lambda: submit_payment_task.delay(payment_id), robust=True)


def _lock_payment(payment_id) -> ExternalPayment:
    return ExternalPayment.objects.select_for_update().get(id=payment_id)


def _lock_accounts(*ids) -> dict:
    # Fixed order (by primary key), the same order banking.services.transfer_funds uses.
    accounts = Account.objects.select_for_update().filter(id__in=ids).order_by("id")
    return {a.id: a for a in accounts}


def _audit(action: str, payment: ExternalPayment, *, actor=None) -> None:
    """Records a payment event. Call after the payment's row and account locks are taken."""
    record(
        action,
        actor=actor,
        organization_id=payment.account.organization_id,
        target=payment,
        metadata={
            "amount": str(payment.amount),
            "currency": payment.currency,
            "rail": payment.rail,
            "reference": payment.reference,
            **({"reason": payment.failure_reason} if payment.failure_reason else {}),
        },
    )


def _flag(payment: ExternalPayment, note: str) -> None:
    logger.warning("Payment %s needs review: %s", payment.reference, note)
    payment.needs_review = True
    payment.review_note = note[:255]
    payment.save(update_fields=["needs_review", "review_note", "updated_at"])


def _post(payment, *, debit: Account, credit: Account, debit_category, credit_category, line_status) -> None:
    """Moves `payment.amount` from `debit` to `credit` and writes both ledger lines. Rows must be locked."""
    amount = payment.amount
    debit.balance -= amount
    credit.balance += amount
    debit.save(update_fields=["balance", "updated_at"])
    credit.save(update_fields=["balance", "updated_at"])

    provider_name = rail_label(payment.rail)
    customer = holder_name(payment.account)
    descriptions = {
        Transaction.Category.DEPOSIT: f"Deposit from {provider_name}",
        Transaction.Category.WITHDRAWAL: payment.metadata.get("description") or f"Sent to {provider_name}",
        Transaction.Category.WITHDRAWAL_REVERSAL: f"Returned: {provider_name} payout failed",
    }
    for account, side, category, balance in (
        (debit, Transaction.Type.DEBIT, debit_category, debit.balance),
        (credit, Transaction.Type.CREDIT, credit_category, credit.balance),
    ):
        on_wallet = account.id == payment.account_id
        Transaction.objects.create(
            account=account,
            type=side,
            category=category,
            status=line_status,
            amount=amount,
            balance_after=balance,
            counterparty_name=provider_name if on_wallet else customer,
            counterparty_account="" if on_wallet else payment.account.account_number,
            description=descriptions[category],
            reference=payment.reference,
        )
    into_wallet = credit.id == payment.account_id
    if payment.account.organization_id and debit_category == Transaction.Category.WITHDRAWAL:
        business_books.record_movement(
            wallet=payment.account, direction="OUT", amount=amount, source=BusinessEntry.Source.PAYOUT,
            reference=payment.reference, counterparty=payment.metadata.get("recipient", "") or provider_name,
            description=descriptions[debit_category][:255], role=payment.metadata.get("books_role") or "drawings",
            actor=payment.initiated_by,
        )  # fmt: skip
    books.book_wallet_movement(
        role=f"provider_clearing:{payment.rail}",
        currency=payment.currency,
        amount=amount,
        into_wallets=into_wallet,
        memo=f"{descriptions[credit_category if into_wallet else debit_category]}: wallet {payment.account.account_number}",
        reference=payment.reference,
    )
