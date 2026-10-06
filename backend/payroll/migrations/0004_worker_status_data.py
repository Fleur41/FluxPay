"""Existing workers: active or deactivated as is_active said, with the name and user of their wallet's owner."""

from django.db import migrations

FIELDS = ["status", "user", "full_name", "activated_at"]


def forwards(apps, schema_editor):
    Worker = apps.get_model("payroll", "Worker")
    batch = []
    for worker in Worker.objects.select_related("wallet__owner").iterator(chunk_size=500):
        worker.status = "ACTIVE" if worker.is_active else "DEACTIVATED"
        worker.user_id = worker.wallet.owner_id
        worker.full_name = worker.wallet.owner.full_name
        worker.activated_at = worker.created_at
        batch.append(worker)
        if len(batch) == 500:
            Worker.objects.bulk_update(batch, FIELDS)
            batch = []
    Worker.objects.bulk_update(batch, FIELDS)


class Migration(migrations.Migration):
    dependencies = [("payroll", "0003_worker_status")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
