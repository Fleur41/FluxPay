"""Payment constraints, once 0004 has filled every row."""

from django.db import migrations, models

WORKER_TYPES = ["SALARY", "ALLOWANCE", "BONUS", "COMMISSION", "OTHER_WORKER"]


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0004_payment_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING_APPROVAL", "Waiting for approval"),
                    ("PENDING", "Not paid yet"),
                    ("PROCESSING", "Processing"),
                    ("COMPLETED", "Paid"),
                    ("FAILED", "Failed"),
                    ("REJECTED", "Rejected"),
                    ("CANCELLED", "Cancelled"),
                    ("REVERSED", "Reversed"),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="reference",
            field=models.CharField(max_length=24, unique=True),
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["organization", "-created_at"], name="organizatio_organiz_68522e_idx"),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                fields=("created_by", "idempotency_key"), name="unique_business_payment_idempotency"
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=models.Q(pay_run__isnull=False),
                fields=("pay_run", "worker", "type"),
                name="unique_pay_run_line",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(
                condition=~models.Q(type__in=WORKER_TYPES) | models.Q(worker__isnull=False),
                name="worker_payment_has_worker",
            ),
        ),
    ]
