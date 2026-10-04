from celery import shared_task

from . import services


@shared_task
def alert_transfer_task(transfer_id, notify_sender=True):
    services.alert_transfer(transfer_id, notify_sender=notify_sender)


@shared_task
def alert_payment_task(payment_id):
    services.alert_payment(payment_id)


@shared_task
def alert_adjustment_task(adjustment_id):
    services.alert_adjustment(adjustment_id)


@shared_task(bind=True, max_retries=services.MAX_ATTEMPTS)
def deliver_notification(self, notification_id):
    try:
        services.deliver(notification_id)
    except Exception as exc:  # deliver() already recorded the error; give the provider time to recover
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries)) from exc
