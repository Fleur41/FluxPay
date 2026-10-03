"""External money movement. Every status change and ledger line for an external payment goes through here.

Rules (see the design doc, "Payment states and money-safety rules"):
- A wallet only changes when a deposit completes, a withdrawal is held, or a held withdrawal is returned.
- Every transition locks the payment row and checks its current status, so a callback and a status
  check racing each other settle a payment once.
- A callback never settles a payment by itself; the outcome always comes from the provider's status API.
- An unclear answer (ProviderState.UNKNOWN, ProviderUnavailable) never fails or reverses a payment.

Lock order is always: payment row, then account rows by primary key. Keep it that way to avoid deadlocks.
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction as db_transaction
from django.utils import timezone
from rest_framework import status

from banking.models import Account, Transaction
from banking.services import new_reference
from fluxpay.exceptions import BusinessError

from .models import ExternalPayment, Rail, WebhookEvent
from .providers import get_provider
from .providers.base import ProviderError, ProviderState, StatusResult

logger = logging.getLogger(__name__)

SYSTEM_USER_EMAIL = "system@fluxpay.internal"

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
# Currencies each rail settles in. A rail missing here (the fake one) accepts any wallet.
RAIL_CURRENCIES = {Rail.MPESA: {"KES"}, Rail.PAYPAL: {"USD"}, Rail.BANK: {"KES"}}
AFTER_SUBMIT = {Direction.IN: Status.PENDING, Direction.OUT: Status.SUBMITTED}


class PaymentNotFound(Exception):
    """A callback names a provider reference we have not recorded (yet)."""


# --- Clearing accounts -------------------------------------------------------------------------


def clearing_account(rail: str, currency: str) -> Account:
    """FluxPay's account mirroring the money held at one provider in one currency. Created on first use."""
    key = f"clearing:{rail}:{currency}"
    account = Account.objects.filter(system_key=key).first()
    if account is not None:
        return account
    owner = _system_user()
    try:
        with db_transaction.atomic():
            return Account.objects.create(
                owner=owner, system_key=key, currency=currency, name=f"{Rail(rail).label} clearing {currency}"
            )
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


# --- Starting payments -------------------------------------------------------------------------


def start_deposit(*, user, account_id, rail: str, method: str, amount: Decimal, idempotency_key: str, metadata=None):
    """Records a deposit and queues its submission to the provider. Returns (payment, created)."""
    existing = _existing(user, idempotency_key)
    if existing:
        return existing, False
    _require_provider(rail)
    account = Account.objects.filter(id=account_id, owner=user, is_active=True, system_key__isnull=True).first()
    if account is None:
        raise BusinessError("Account not found.", "account_not_found", status.HTTP_404_NOT_FOUND)
    _require_currency(rail, account.currency)

    try:
        with db_transaction.atomic():
            payment = ExternalPayment.objects.create(
                account=account,
                initiated_by=user,
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
            _queue_submit(payment)
    except IntegrityError:
        return ExternalPayment.objects.get(initiated_by=user, idempotency_key=idempotency_key), False
    return payment, True


def start_payout(*, user, account_id, rail: str, method: str, amount: Decimal, idempotency_key: str, metadata=None):
    """Takes the money out of the wallet (HELD) and queues the payout. Returns (payment, created)."""
    existing = _existing(user, idempotency_key)
    if existing:
        return existing, False
    _require_provider(rail)
    if amount > settings.FLUXPAY_MAX_TRANSFER:
        raise BusinessError(
            f"Withdrawals are limited to {settings.FLUXPAY_MAX_TRANSFER:,.2f} per transaction.", "limit_exceeded"
        )
    wallet = Account.objects.filter(id=account_id, owner=user, is_active=True, system_key__isnull=True).first()
    if wallet is None:
        raise BusinessError("Account not found.", "account_not_found", status.HTTP_404_NOT_FOUND)
    _require_currency(rail, wallet.currency)
    clearing = clearing_account(rail, wallet.currency)

    try:
        with db_transaction.atomic():
            locked = _lock_accounts(wallet.id, clearing.id)
            wallet, clearing = locked[wallet.id], locked[clearing.id]
            if wallet.balance < amount:
                raise BusinessError("Insufficient funds for this withdrawal.", "insufficient_funds")
            payment = ExternalPayment.objects.create(
                account=wallet,
                initiated_by=user,
                direction=Direction.OUT,
                rail=rail,
                method=method,
                status=Status.HELD,
                amount=amount,
                currency=wallet.currency,
                reference=new_reference(),
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
            _queue_submit(payment)
    except IntegrityError:
        return ExternalPayment.objects.get(initiated_by=user, idempotency_key=idempotency_key), False
    return payment, True


def submit_payment(payment_id) -> ExternalPayment:
    """Sends a CREATED deposit or HELD payout to its provider. Safe to call again (payouts are idempotent).

    ProviderUnavailable propagates so the caller (a Celery task) retries; the payment keeps its status.
    """
    payment = ExternalPayment.objects.get(id=payment_id)
    if payment.status != SUBMITTABLE[payment.direction]:
        return payment
    provider = get_provider(payment.rail)
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
        else:
            Transaction.objects.filter(reference=payment.reference, status=Transaction.Status.PENDING).update(
                status=Transaction.Status.COMPLETED
            )

        payment.status = Status.COMPLETED
        payment.completed_at = timezone.now()
        if result.provider_ref and not payment.provider_ref:
            payment.provider_ref = result.provider_ref
        payment.save(update_fields=["status", "completed_at", "provider_ref", "updated_at"])
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
            payment.status = Status.REVERSED
        payment.failure_reason = reason[:255]
        payment.save(update_fields=["status", "failure_reason", "updated_at"])
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

            db_transaction.on_commit(lambda: process_webhook_event.delay(str(event.id)))
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


def _existing(user, idempotency_key: str):
    return ExternalPayment.objects.filter(initiated_by=user, idempotency_key=idempotency_key).first()


def _require_provider(rail: str) -> None:
    try:
        get_provider(rail)
    except LookupError:
        raise BusinessError("This payment method isn't available.", "rail_unavailable") from None


def _require_currency(rail: str, currency: str) -> None:
    allowed = RAIL_CURRENCIES.get(rail)
    if allowed is not None and currency not in allowed:
        raise BusinessError(
            f"{Rail(rail).label} works with {', '.join(sorted(allowed))} wallets, not {currency}.",
            "currency_not_supported",
        )


def _queue_submit(payment: ExternalPayment) -> None:
    from .tasks import submit_payment_task

    payment_id = str(payment.id)
    db_transaction.on_commit(lambda: submit_payment_task.delay(payment_id))


def _lock_payment(payment_id) -> ExternalPayment:
    return ExternalPayment.objects.select_for_update().get(id=payment_id)


def _lock_accounts(*ids) -> dict:
    # Fixed order (by primary key), the same order banking.services.transfer_funds uses.
    accounts = Account.objects.select_for_update().filter(id__in=ids).order_by("id")
    return {a.id: a for a in accounts}


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

    provider_name = Rail(payment.rail).label
    customer = payment.account.owner.full_name
    descriptions = {
        Transaction.Category.DEPOSIT: f"Deposit from {provider_name}",
        Transaction.Category.WITHDRAWAL: f"Sent to {provider_name}",
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
