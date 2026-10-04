"""Money movement. Every balance change goes through here, inside a DB transaction."""
import secrets
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction as db_transaction
from rest_framework import status

from audit.services import record
from fluxpay.exceptions import BusinessError
from platform_settings import services as rules

from .models import Account, ManualAdjustment, Transaction, Transfer
from .signals import adjustment_posted, transfer_completed


def new_reference() -> str:
    return "FP" + secrets.token_hex(6).upper()


SYSTEM_USER_EMAIL = "system@fluxpay.internal"


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
    return account


def post_adjustment(*, staff, account_id, kind: str, amount: Decimal, reason: str) -> ManualAdjustment:
    """A staff top-up (CREDIT) or correction (DEBIT) of a customer or business wallet.

    The money comes from, or goes back to, the "Manual adjustments" system account, so the ledger still
    balances. The currency's per-transaction limits apply (a guard against typing an extra zero), and a
    correction can never take a wallet below zero. Permission is checked by the caller (the admin).
    """
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise BusinessError("Give a reason of at least 10 characters for the audit trail.", "reason_required")
    target = Account.objects.filter(id=account_id, system_key__isnull=True).first()
    if target is None:
        raise BusinessError("Customer wallet not found.", "account_not_found", status.HTTP_404_NOT_FOUND)
    if not target.is_active:
        raise BusinessError("This wallet is closed.", "account_inactive")
    rules.check_amount(amount, target.currency)
    pool = system_account(f"adjustments:{target.currency}", f"Manual adjustments {target.currency}", target.currency)

    with db_transaction.atomic():
        rows = Account.objects.select_for_update().filter(id__in=[target.id, pool.id]).order_by("id")
        locked = {a.id: a for a in rows}
        target, pool = locked[target.id], locked[pool.id]
        credit = kind == ManualAdjustment.Kind.CREDIT
        if not credit and target.balance < amount:
            raise BusinessError(
                f"The wallet only holds {target.balance:,.2f} {target.currency}; "
                "a correction can't take it below zero.",
                "insufficient_funds",
            )
        source, destination = (pool, target) if credit else (target, pool)
        source.balance -= amount
        destination.balance += amount
        source.save(update_fields=["balance", "updated_at"])
        destination.save(update_fields=["balance", "updated_at"])

        reference = new_reference()
        description = "Top-up by FluxPay" if credit else "Correction by FluxPay"
        for line_account, side in ((source, Transaction.Type.DEBIT), (destination, Transaction.Type.CREDIT)):
            on_wallet = line_account.id == target.id
            Transaction.objects.create(
                account=line_account,
                type=side,
                category=Transaction.Category.ADJUSTMENT,
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
        )
        record(
            "adjustment.credited" if credit else "adjustment.debited",
            actor=staff,
            organization_id=target.organization_id,
            target=adjustment,
            metadata={
                "account": target.account_number,
                "amount": str(amount),
                "currency": target.currency,
                "reason": reason,
                "reference": reference,
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
                               note: str, idempotency_key: str):
    """Moves money from a business wallet. The caller (organizations.services) has already checked the
    member's permission and any approval; this only confirms the wallet belongs to the organization."""
    return _transfer(
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
              idempotency_key: str):
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

            reference = new_reference()
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
            transfer_completed.send(sender=Transfer, transfer=transfer)
            return transfer, debit, True
    except IntegrityError:
        # A concurrent request with the same idempotency key won the race.
        existing = Transfer.objects.get(initiated_by=initiator, idempotency_key=idempotency_key)
        return existing, _debit_for(existing), False


def _debit_for(transfer: Transfer) -> Transaction:
    return Transaction.objects.get(reference=transfer.reference, type=Transaction.Type.DEBIT)
