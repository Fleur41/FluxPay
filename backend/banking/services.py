"""Money movement. Every balance change goes through here, inside a DB transaction."""
import secrets
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction as db_transaction
from rest_framework import status

from fluxpay.exceptions import BusinessError

from .models import Account, Transaction, Transfer


def new_reference() -> str:
    return "FP" + secrets.token_hex(6).upper()


@db_transaction.atomic
def open_wallet(user, currency: str | None = None, name: str = "Main Wallet") -> Account:
    account = Account.objects.create(owner=user, currency=currency or settings.FLUXPAY_DEFAULT_CURRENCY, name=name)
    bonus = settings.FLUXPAY_SIGNUP_BONUS
    if bonus > 0:
        account.balance = bonus
        account.save(update_fields=["balance", "updated_at"])
        Transaction.objects.create(
            account=account,
            type=Transaction.Type.CREDIT,
            category=Transaction.Category.BONUS,
            amount=bonus,
            balance_after=bonus,
            counterparty_name="FluxPay",
            description="Welcome bonus",
            reference=new_reference(),
        )
    return account


def transfer_funds(*, user, source_id, destination_number: str, amount: Decimal, note: str, idempotency_key: str):
    """Moves money between two accounts. Returns (transfer, debit_transaction, created)."""
    existing = Transfer.objects.filter(initiated_by=user, idempotency_key=idempotency_key).first()
    if existing:
        return existing, _debit_for(existing), False

    if amount > settings.FLUXPAY_MAX_TRANSFER:
        raise BusinessError(
            f"Transfers are limited to {settings.FLUXPAY_MAX_TRANSFER:,.2f} per transaction.", "limit_exceeded"
        )

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
            if source is None or source.owner_id != user.id or not source.is_active:
                raise BusinessError("Source account not found.", "account_not_found", status.HTTP_404_NOT_FOUND)
            if source.id == destination.id:
                raise BusinessError("You can't send money to the same account.", "same_account")
            if source.currency != destination.currency:
                raise BusinessError(
                    f"Currency mismatch: {source.currency} → {destination.currency}. Cross-currency transfers aren't supported yet.",
                    "currency_mismatch",
                )
            if source.balance < amount:
                raise BusinessError("Insufficient funds for this transfer.", "insufficient_funds")

            reference = new_reference()
            source.balance -= amount
            destination.balance += amount
            source.save(update_fields=["balance", "updated_at"])
            destination.save(update_fields=["balance", "updated_at"])

            transfer = Transfer.objects.create(
                initiated_by=user,
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
                counterparty_name=destination.owner.full_name,
                counterparty_account=destination.account_number,
                description=note or f"Sent to {destination.owner.full_name}",
                reference=reference,
            )
            Transaction.objects.create(
                account=destination,
                type=Transaction.Type.CREDIT,
                category=Transaction.Category.TRANSFER_IN,
                amount=amount,
                balance_after=destination.balance,
                counterparty_name=source.owner.full_name,
                counterparty_account=source.account_number,
                description=note or f"Received from {source.owner.full_name}",
                reference=reference,
            )
            return transfer, debit, True
    except IntegrityError:
        # A concurrent request with the same idempotency key won the race.
        existing = Transfer.objects.get(initiated_by=user, idempotency_key=idempotency_key)
        return existing, _debit_for(existing), False


def _debit_for(transfer: Transfer) -> Transaction:
    return Transaction.objects.get(reference=transfer.reference, type=Transaction.Type.DEBIT)
