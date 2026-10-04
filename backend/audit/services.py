"""Writing and verifying the audit log.

Call `record` inside the same database transaction as the action it describes, so the event and
the action commit or roll back together.

Locking: `record` locks the single chain-head row until the transaction commits. Take every other
row lock (accounts, payments) BEFORE the first `record` in a transaction, never after, or two
transactions can deadlock (one holding an account and wanting the head, the other the reverse).
"""
import hashlib
import json
from contextvars import ContextVar

from django.db import transaction as db_transaction
from django.utils import timezone

from .models import AuditChainHead, AuditEvent

GENESIS_HASH = "0" * 64

# Set per request by AuditContextMiddleware; empty in background jobs.
request_context: ContextVar[dict] = ContextVar("audit_request_context", default={})


def record(action: str, *, actor=None, organization_id=None, target=None, metadata=None) -> AuditEvent:
    """Appends one event. `target` is a model instance (or None); `metadata` must be JSON-safe."""
    context = request_context.get()
    fields = {
        "created_at": timezone.now(),
        "actor_id": actor.pk if actor is not None else None,
        "actor_label": actor.email if actor is not None else "system",
        "organization_id": organization_id,
        "action": action,
        "target_type": target._meta.label if target is not None else "",
        "target_id": str(target.pk) if target is not None else "",
        "metadata": metadata or {},
        "ip_address": context.get("ip_address"),
        "user_agent": context.get("user_agent", ""),
    }
    with db_transaction.atomic():
        AuditChainHead.objects.get_or_create(pk=1, defaults={"last_hash": GENESIS_HASH})
        head = AuditChainHead.objects.select_for_update().get(pk=1)
        event = AuditEvent(**fields, prev_hash=head.last_hash)
        event.hash = compute_hash(event)
        event.save()
        head.last_hash = event.hash
        head.save(update_fields=["last_hash"])
    return event


def compute_hash(event: AuditEvent) -> str:
    payload = json.dumps(
        {
            "created_at": event.created_at.isoformat(),
            "actor_id": str(event.actor_id) if event.actor_id else None,
            "actor_label": event.actor_label,
            "organization_id": str(event.organization_id) if event.organization_id else None,
            "action": event.action,
            "target_type": event.target_type,
            "target_id": event.target_id,
            "metadata": event.metadata,
            "ip_address": event.ip_address,
            "user_agent": event.user_agent,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256((event.prev_hash + payload).encode()).hexdigest()


def verify_chain() -> int | None:
    """Returns the id of the first event that fails verification, or None if the whole log is intact."""
    expected_prev = GENESIS_HASH
    for event in AuditEvent.objects.order_by("id").iterator(chunk_size=2000):
        if event.prev_hash != expected_prev or compute_hash(event) != event.hash:
            return event.id
        expected_prev = event.hash
    head = AuditChainHead.objects.filter(pk=1).first()
    if head is not None and head.last_hash != expected_prev:
        return -1  # events were deleted from the end of the log
    return None
