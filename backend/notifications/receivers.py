"""Queue alerts when money moves. Nothing is sent until the money movement has committed."""
from django.db import transaction as db_transaction
from django.dispatch import receiver

from banking.signals import adjustment_posted, transfer_completed
from payments.signals import payment_settled


@receiver(transfer_completed)
def on_transfer_completed(sender, transfer, **kwargs):
    from .tasks import alert_transfer_task

    transfer_id = str(transfer.id)
    db_transaction.on_commit(lambda: alert_transfer_task.delay(transfer_id), robust=True)


@receiver(payment_settled)
def on_payment_settled(sender, payment, **kwargs):
    from .tasks import alert_payment_task

    payment_id = str(payment.id)
    db_transaction.on_commit(lambda: alert_payment_task.delay(payment_id), robust=True)


@receiver(adjustment_posted)
def on_adjustment_posted(sender, adjustment, **kwargs):
    from .tasks import alert_adjustment_task

    adjustment_id = str(adjustment.id)
    db_transaction.on_commit(lambda: alert_adjustment_task.delay(adjustment_id), robust=True)
