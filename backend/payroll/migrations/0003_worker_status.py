"""Workers get a status (invited, waiting for approval, active, suspended, deactivated) instead of is_active,
and can exist before they have a wallet: an invitation, or a join request. 0004 fills the new fields from
each worker's wallet; 0005 adds the constraints and drops is_active.

Split in three because PostgreSQL can't alter a table in the transaction that just updated its rows.
"""

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0002_remove_payslip"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="worker",
            name="status",
            field=models.CharField(
                choices=[
                    ("INVITED", "Invited"),
                    ("PENDING_ACTIVATION", "Waiting for approval"),
                    ("ACTIVE", "Active"),
                    ("SUSPENDED", "Suspended"),
                    ("DEACTIVATED", "Deactivated"),
                ],
                db_index=True,
                default="ACTIVE",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="worker",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="employments",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="worker",
            name="wallet",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="employments",
                to="banking.account",
            ),
        ),
        migrations.AddField(
            model_name="worker",
            name="full_name",
            field=models.CharField(default="", max_length=150),
            preserve_default=False,
        ),
        migrations.AddField(model_name="worker", name="phone_number", field=models.CharField(blank=True, max_length=16)),
        migrations.AddField(model_name="worker", name="email", field=models.EmailField(blank=True, max_length=254)),
        migrations.AlterField(
            model_name="worker",
            name="salary",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AddField(
            model_name="worker",
            name="invite_code_hash",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="worker", name="invite_expires_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AddField(model_name="worker", name="activated_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="worker", name="status_note", field=models.CharField(blank=True, max_length=255)),
    ]
