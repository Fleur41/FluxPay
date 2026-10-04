from django.core.management.base import BaseCommand, CommandError

from audit.models import AuditEvent
from audit.services import verify_chain


class Command(BaseCommand):
    help = "Checks the audit log's hash chain. Exits with an error if any event was changed or removed."

    def handle(self, *args, **options):
        broken = verify_chain()
        if broken == -1:
            raise CommandError("Audit log is broken: events were removed from the end of the log.")
        if broken is not None:
            raise CommandError(f"Audit log is broken at event #{broken}: it, or the event before it, was altered.")
        self.stdout.write(self.style.SUCCESS(f"Audit log intact ({AuditEvent.objects.count()} events)."))
