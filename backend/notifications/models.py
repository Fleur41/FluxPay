import uuid

from django.conf import settings
from django.db import models


class NotificationSettings(models.Model):
    """Which channels a user wants transaction alerts on. Created on first read, both on."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, related_name="notification_settings"
    )
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user} email={self.email_enabled} sms={self.sms_enabled}"


class Notification(models.Model):
    """One alert on one channel. The unique key makes a retried event never alert twice."""

    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    channel = models.CharField(max_length=5, choices=Channel.choices)
    event = models.CharField(max_length=40)  # e.g. "transfer.sent", "payment.deposit_completed"
    reference = models.CharField(max_length=40)  # the transfer or payment reference it is about
    destination = models.CharField(max_length=254)  # email address or E.164 phone number at send time
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    provider_message_id = models.CharField(max_length=100, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("user", "channel", "event", "reference"), name="unique_notification")
        ]

    def __str__(self) -> str:
        return f"{self.channel} {self.event} {self.reference} -> {self.user} ({self.status})"
