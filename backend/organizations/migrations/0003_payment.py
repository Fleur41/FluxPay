"""PaymentRequest becomes Payment: every payment out of a business cashbook, with a type, a recipient and its
own reference. 0004 fills the new fields and moves pay-run payslips in; 0005 adds the constraints.

Split in three because PostgreSQL can't alter a table in the transaction that just bulk-inserted into it.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0002_payment_books_category"),
        ("payroll", "0001_initial"),
        ("banking", "0009_one_cashbook_per_business"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="paymentrequest", name="unique_payment_request_idempotency"),
        migrations.RenameModel(old_name="PaymentRequest", new_name="Payment"),
        migrations.AlterField(
            model_name="payment",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="organizations.organization"
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="transfer",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payment",
                to="banking.transfer",
            ),
        ),
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
                    ("EXECUTED", "Sent"),  # only until forwards() has run
                ],
                db_index=True,
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="type",
            field=models.CharField(
                choices=[
                    ("SALARY", "Salary"),
                    ("ALLOWANCE", "Allowance"),
                    ("BONUS", "Bonus"),
                    ("COMMISSION", "Commission"),
                    ("OTHER_WORKER", "Other worker payment"),
                    ("SUPPLIER", "Supplier payment"),
                    ("VENDOR", "Vendor payment"),
                    ("CONTRACTOR", "Contractor payment"),
                    ("EXPENSE", "Business expense"),
                    ("OTHER", "Other payment"),
                ],
                default="SUPPLIER",
                max_length=12,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="payment",
            name="worker",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="payroll.worker",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="pay_run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payslips",
                to="payroll.payrun",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="recipient_name",
            field=models.CharField(default="", max_length=150),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="payment",
            name="reference",
            field=models.CharField(max_length=24, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="reversal",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reversed_payment",
                to="banking.transfer",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="reversed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="reversed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="reversal_reason",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="payment",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
