from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Append-only, hash-chained record of security- and money-relevant actions.

    Each event's hash covers its own fields and the previous event's hash, so changing or deleting
    any past event breaks every hash after it (see audit.services.verify_chain).
    Written only through audit.services.record.
    """

    id = models.BigAutoField(primary_key=True)  # chain order
    created_at = models.DateTimeField(db_index=True)
    # Null for actions the system takes by itself (scheduled jobs, provider callbacks).
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="audit_events"
    )
    actor_label = models.CharField(max_length=254)  # the actor's email when it happened, or "system"
    # Not a foreign key, so the audit log never depends on (or blocks deleting from) other apps.
    organization_id = models.UUIDField(null=True, blank=True, db_index=True)
    action = models.CharField(max_length=64, db_index=True)  # e.g. "org.member.invited"
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ("-id",)
        indexes = [models.Index(fields=("organization_id", "-id"))]

    def __str__(self) -> str:
        return f"#{self.id} {self.action} by {self.actor_label}"


class AuditChainHead(models.Model):
    """One row holding the latest hash. Locking it serialises appends so the chain never forks."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    last_hash = models.CharField(max_length=64)
