"""Payslips now live in organizations.Payment (copied there by organizations 0004, ids kept)."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0001_initial"),
        ("organizations", "0005_payment_constraints"),
    ]

    operations = [
        migrations.DeleteModel(name="Payslip"),
    ]
