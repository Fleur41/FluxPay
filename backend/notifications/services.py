"""Transaction alerts by email and SMS.

Flow: a settlement signal (banking/payments) -> receivers queue an alert job after commit ->
`alert_transfer` / `alert_payment` decide who is told what and create one Notification per channel ->
`deliver` sends each one (retried by the task on failure). The unique key on Notification means a
re-run never alerts anyone twice.
"""
from dataclasses import dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction as db_transaction
from django.utils import timezone

from banking.models import Account, ManualAdjustment, Transaction, Transfer
from banking.services import holder_name
from organizations.models import Membership
from payments.models import ExternalPayment, rail_label

from .models import Notification, NotificationSettings
from .sms import get_sms_backend, normalize_phone

MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class Alert:
    event: str
    reference: str
    subject: str  # email subject
    email_body: str
    sms_body: str  # kept short: one SMS is 160 characters


# --- Building alerts ----------------------------------------------------------------------------


def alert_transfer(transfer_id) -> list[Notification]:
    """Tells the sending side and the receiving side of a transfer."""
    transfer = Transfer.objects.select_related(
        "source__owner", "source__organization", "destination__owner", "destination__organization"
    ).get(id=transfer_id)
    lines = {line.type: line for line in Transaction.objects.filter(reference=transfer.reference)}
    debit, credit = lines.get(Transaction.Type.DEBIT), lines.get(Transaction.Type.CREDIT)
    when = _local_time(transfer.created_at)
    amount = _money(transfer.amount, transfer.source.currency)
    sender, recipient = holder_name(transfer.source), holder_name(transfer.destination)
    note = f'\nNote: "{transfer.note}"' if transfer.note else ""

    created = []
    if debit:
        whose = _whose(transfer.source)
        balance = _money(debit.balance_after, transfer.source.currency)
        created += _queue_for(
            transfer.source,
            Alert(
                event="transfer.sent",
                reference=transfer.reference,
                subject=f"{whose} sent {amount} to {recipient}",
                email_body=(
                    f"{whose} sent {amount} to {recipient} ({_mask(transfer.destination.account_number)}) "
                    f"on {when}.{note}\n\nReference: {transfer.reference}\nNew balance: {balance}\n"
                ),
                sms_body=(
                    f"FluxPay: {whose} sent {amount} to {recipient} ({_mask(transfer.destination.account_number)}) "
                    f"on {when}. Ref {transfer.reference}. Bal {balance}."
                ),
            ),
        )
    if credit:
        whose = _whose(transfer.destination)
        balance = _money(credit.balance_after, transfer.destination.currency)
        created += _queue_for(
            transfer.destination,
            Alert(
                event="transfer.received",
                reference=transfer.reference,
                subject=f"{whose} received {amount} from {sender}",
                email_body=(
                    f"{whose} received {amount} from {sender} ({_mask(transfer.source.account_number)}) "
                    f"on {when}.{note}\n\nReference: {transfer.reference}\nNew balance: {balance}\n"
                ),
                sms_body=(
                    f"FluxPay: {whose} received {amount} from {sender} ({_mask(transfer.source.account_number)}) "
                    f"on {when}. Ref {transfer.reference}. Bal {balance}."
                ),
            ),
        )
    return created


def alert_payment(payment_id) -> list[Notification]:
    """Tells the wallet's people how a deposit or payout through an outside provider ended."""
    payment = ExternalPayment.objects.select_related("account__owner", "account__organization").get(id=payment_id)
    amount = _money(payment.amount, payment.currency)
    rail = rail_label(payment.rail)
    when = _local_time(payment.completed_at or payment.updated_at)
    whose = _whose(payment.account)
    balance = _money(payment.account.balance, payment.currency)
    receipt = payment.metadata.get("provider_receipt")
    receipt_line = f"\n{rail} receipt: {receipt}" if receipt else ""
    ref = payment.reference

    S, D = ExternalPayment.Status, ExternalPayment.Direction
    if payment.direction == D.IN and payment.status == S.COMPLETED:
        alert = Alert(
            "payment.deposit_completed", ref, f"{whose} added {amount} from {rail}",
            f"{whose} added {amount} from {rail} on {when}.\n\nReference: {ref}{receipt_line}\nNew balance: {balance}\n",
            f"FluxPay: {whose} added {amount} from {rail} on {when}. Ref {ref}. Bal {balance}.",
        )
    elif payment.direction == D.IN and payment.status == S.FAILED:
        alert = Alert(
            "payment.deposit_failed", ref, f"Your {rail} top-up of {amount} didn't go through",
            f"Your {rail} top-up of {amount} didn't go through: {payment.failure_reason or 'not completed'}.\n"
            f"No money was taken.\n\nReference: {ref}\n",
            f"FluxPay: Your {rail} top-up of {amount} didn't go through. No money was taken. Ref {ref}.",
        )
    elif payment.direction == D.OUT and payment.status == S.COMPLETED:
        alert = Alert(
            "payment.payout_completed", ref, f"{whose} sent {amount} to {rail}",
            f"{whose} sent {amount} to {rail} on {when}.\n\nReference: {ref}\nNew balance: {balance}\n",
            f"FluxPay: {whose} sent {amount} to {rail} on {when}. Ref {ref}. Bal {balance}.",
        )
    elif payment.direction == D.OUT and payment.status == S.REVERSED:
        alert = Alert(
            "payment.payout_reversed", ref, f"Your {amount} {rail} payout failed: money returned",
            f"Your {amount} payout to {rail} failed and the money was returned to your wallet.\n"
            f"Reason: {payment.failure_reason or 'declined'}\n\nReference: {ref}\nNew balance: {balance}\n",
            f"FluxPay: Your {amount} payout to {rail} failed. The money is back in your wallet. Ref {ref}. Bal {balance}.",
        )
    else:
        return []
    return _queue_for(payment.account, alert)


def alert_adjustment(adjustment_id) -> list[Notification]:
    """Tells the wallet's people about a staff top-up or correction."""
    adjustment = ManualAdjustment.objects.select_related("account__owner", "account__organization").get(
        id=adjustment_id
    )
    account, ref = adjustment.account, adjustment.reference
    amount = _money(adjustment.amount, account.currency)
    balance = _money(adjustment.balance_after, account.currency)
    when = _local_time(adjustment.created_at)
    wallet = "your wallet" if account.organization_id is None else f"{account.organization.name}'s wallet"
    masked = _mask(account.account_number)
    if adjustment.kind == ManualAdjustment.Kind.CREDIT:
        alert = Alert(
            "adjustment.credited", ref, f"FluxPay added {amount} to {wallet}",
            f"FluxPay added {amount} to {wallet} ({masked}) on {when}.\n\nReference: {ref}\nNew balance: {balance}\n",
            f"FluxPay: {amount} added to {wallet} ({masked}) on {when}. Ref {ref}. Bal {balance}.",
        )
    else:
        alert = Alert(
            "adjustment.debited", ref, f"FluxPay corrected {wallet}: {amount} deducted",
            f"FluxPay corrected {wallet} ({masked}) on {when}: {amount} was deducted.\n"
            "Questions? Contact FluxPay support with the reference below.\n\n"
            f"Reference: {ref}\nNew balance: {balance}\n",
            f"FluxPay: {amount} deducted from {wallet} ({masked}) as a correction on {when}. Ref {ref}. Bal {balance}.",
        )
    return _queue_for(account, alert)


# --- Queueing and delivery ----------------------------------------------------------------------


def settings_for(user) -> NotificationSettings:
    prefs, _ = NotificationSettings.objects.get_or_create(user=user)
    return prefs


def deliver(notification_id) -> Notification:
    """Sends one notification. Raises on failure (the task retries) until MAX_ATTEMPTS, then marks it FAILED."""
    with db_transaction.atomic():
        notification = Notification.objects.select_for_update().get(id=notification_id)
        if notification.status != Notification.Status.QUEUED:
            return notification
        notification.attempts += 1
        notification.save(update_fields=["attempts"])
    try:
        if notification.channel == Notification.Channel.EMAIL:
            send_mail(notification.subject, notification.body, None, [notification.destination])
            message_id = ""
        else:
            message_id = get_sms_backend().send(notification.destination, notification.body)
    except Exception as exc:
        notification.error = f"{type(exc).__name__}: {exc}"[:2000]
        if notification.attempts >= MAX_ATTEMPTS:
            notification.status = Notification.Status.FAILED
            notification.save(update_fields=["error", "status"])
            return notification
        notification.save(update_fields=["error"])
        raise
    notification.status, notification.sent_at = Notification.Status.SENT, timezone.now()
    notification.provider_message_id = message_id[:100]
    notification.save(update_fields=["status", "sent_at", "provider_message_id"])
    return notification


def _queue_for(account: Account, alert: Alert) -> list[Notification]:
    created = []
    for user in _people_to_alert(account):
        prefs = settings_for(user)
        channels = []
        if prefs.email_enabled and user.email:
            channels.append((Notification.Channel.EMAIL, user.email, alert.subject, alert.email_body))
        phone = normalize_phone(user.phone_number)
        if prefs.sms_enabled and phone:
            channels.append((Notification.Channel.SMS, phone, "", alert.sms_body))
        for channel, destination, subject, body in channels:
            try:
                with db_transaction.atomic():
                    notification = Notification.objects.create(
                        user=user, channel=channel, event=alert.event, reference=alert.reference,
                        destination=destination, subject=subject, body=body,
                    )
            except IntegrityError:
                continue  # this alert was already queued (the job ran before)
            created.append(notification)
    from .tasks import deliver_notification

    for notification in created:
        notification_id = str(notification.id)
        db_transaction.on_commit(lambda nid=notification_id: deliver_notification.delay(nid), robust=True)
    return created


def _people_to_alert(account: Account) -> list:
    """A personal wallet's owner; for a business wallet, its active owners and admins."""
    if account.organization_id is None:
        return [account.owner] if account.owner.is_active else []
    memberships = Membership.objects.select_related("user").filter(
        organization_id=account.organization_id,
        is_active=True,
        role__in=(Membership.Role.OWNER, Membership.Role.ADMIN),
        user__is_active=True,
    )
    return [m.user for m in memberships]


def _whose(account: Account) -> str:
    return account.organization.name if account.organization_id else "You"


def _money(amount: Decimal, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


def _mask(account_number: str) -> str:
    return f"••{account_number[-4:]}"


def _local_time(moment) -> str:
    return timezone.localtime(moment, ZoneInfo(settings.FLUXPAY_DISPLAY_TIMEZONE)).strftime("%d %b %Y %H:%M")
