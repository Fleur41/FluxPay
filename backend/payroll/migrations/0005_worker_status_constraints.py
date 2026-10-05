"""Worker constraints, once 0004 has filled every row; is_active is replaced by status."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payroll", "0004_worker_status_data")]

    operations = [
        migrations.RemoveField(model_name="worker", name="is_active"),
        migrations.RemoveConstraint(model_name="worker", name="unique_worker_wallet"),
        migrations.AddConstraint(
            model_name="worker",
            constraint=models.UniqueConstraint(
                condition=models.Q(wallet__isnull=False) & ~models.Q(status="DEACTIVATED"),
                fields=("organization", "wallet"),
                name="unique_worker_wallet",
            ),
        ),
        migrations.AlterModelOptions(name="worker", options={"ordering": ("full_name",)}),
        migrations.AddConstraint(
            model_name="worker",
            constraint=models.UniqueConstraint(
                condition=models.Q(user__isnull=False) & ~models.Q(status="DEACTIVATED"),
                fields=("organization", "user"),
                name="one_open_worker_record_per_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="worker",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="INVITED") & ~models.Q(phone_number=""),
                fields=("organization", "phone_number"),
                name="one_pending_invitation_per_phone",
            ),
        ),
        migrations.AddConstraint(
            model_name="worker",
            constraint=models.CheckConstraint(
                condition=~models.Q(status__in=["ACTIVE", "SUSPENDED"])
                | (models.Q(wallet__isnull=False) & models.Q(salary__isnull=False)),
                name="working_worker_has_wallet_and_salary",
            ),
        ),
    ]
