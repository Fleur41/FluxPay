"""Background work for external payments. Every task is safe to run more than once."""
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from . import services
from .models import ExternalPayment
from .providers.base import ProviderUnavailable

Status = ExternalPayment.Status

# A provider outage retries with backoff (1s, 2s, 4s ... capped at 10 minutes); the payment keeps its status.
RETRY_ON_OUTAGE = {
    "autoretry_for": (ProviderUnavailable,),
    "retry_backoff": True,
    "retry_backoff_max": 600,
    "max_retries": 8,
}
BATCH = 200


@shared_task(**RETRY_ON_OUTAGE)
def submit_payment_task(payment_id):
    services.submit_payment(payment_id)


@shared_task(**RETRY_ON_OUTAGE)
def check_payment_task(payment_id):
    services.check_with_provider(payment_id)


@shared_task(**RETRY_ON_OUTAGE)
def expire_deposit_task(payment_id):
    services.expire_if_abandoned(payment_id)


@shared_task(bind=True, **RETRY_ON_OUTAGE)
def process_webhook_event(self, event_id):
    try:
        services.process_webhook(event_id)
    except services.PaymentNotFound as exc:
        # The callback can arrive before the submit response gave us the provider reference.
        if self.request.retries >= settings.FLUXPAY_WEBHOOK_MATCH_RETRIES:
            services.give_up_on_webhook(event_id, f"No payment with provider reference {exc}")
            return
        raise self.retry(exc=exc, countdown=30) from exc


@shared_task
def resolve_stuck_payments():
    """Catches payments a lost job or a missing callback left behind."""
    cutoff = timezone.now() - timedelta(seconds=settings.FLUXPAY_STATUS_CHECK_AFTER_SECONDS)
    stuck = ExternalPayment.objects.filter(updated_at__lt=cutoff)
    # Never got a provider reference: submit again (payouts are idempotent on our reference).
    for payment_id in stuck.filter(status__in=[Status.CREATED, Status.HELD]).values_list("id", flat=True)[:BATCH]:
        submit_payment_task.delay(str(payment_id))
    for payment_id in stuck.filter(status__in=[Status.PENDING, Status.SUBMITTED]).values_list("id", flat=True)[:BATCH]:
        check_payment_task.delay(str(payment_id))


@shared_task
def expire_abandoned_deposits():
    cutoff = timezone.now() - timedelta(minutes=settings.FLUXPAY_DEPOSIT_EXPIRY_MINUTES)
    abandoned = ExternalPayment.objects.filter(
        direction=ExternalPayment.Direction.IN, status__in=[Status.CREATED, Status.PENDING], created_at__lt=cutoff
    )
    for payment_id in abandoned.values_list("id", flat=True)[:BATCH]:
        expire_deposit_task.delay(str(payment_id))
