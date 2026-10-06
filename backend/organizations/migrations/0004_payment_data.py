"""Fills in the new payment fields, and copies pay-run payslips (payroll.Payslip) into payments with `pay_run`
set, keeping their ids so payslip links keep working. payroll 0002 then drops the payslip table.
"""

import secrets

from django.db import migrations

# Old payments only had a books category; their type follows from it (all were to an account number).
TYPE_FROM_CATEGORY = {"suppliers": "SUPPLIER", "": "SUPPLIER", "expenses": "EXPENSE"}
PAYSLIP_STATUS = {"PAID": "COMPLETED", "REVERSED": "REVERSED"}
UNPAID_IN_RUN = {"CANCELLED": "CANCELLED", "REJECTED": "REJECTED"}


def _reference():
    return "FP" + secrets.token_hex(6).upper()


def forwards(apps, schema_editor):
    Payment = apps.get_model("organizations", "Payment")
    Payslip = apps.get_model("payroll", "Payslip")
    Account = apps.get_model("banking", "Account")
    Permission = apps.get_model("auth", "Permission")

    for payment in Payment.objects.select_related("transfer"):
        payment.type = TYPE_FROM_CATEGORY.get(payment.books_category, "OTHER")
        account = Account.objects.select_related("owner", "organization").filter(
            account_number=payment.destination_account_number
        ).first()
        if account is not None:
            payment.recipient_name = account.organization.name if account.organization_id else account.owner.full_name
        if payment.status == "EXECUTED":
            payment.status = "COMPLETED"
        if payment.transfer_id:
            payment.reference, payment.completed_at = payment.transfer.reference, payment.transfer.created_at
        else:
            payment.reference = _reference()
        payment.save(update_fields=["type", "recipient_name", "status", "reference", "completed_at"])

    payslips = Payslip.objects.select_related("pay_run", "worker__wallet__owner", "transfer").order_by("pk")
    batch = []
    for payslip in payslips.iterator(chunk_size=500):
        run = payslip.pay_run
        status = PAYSLIP_STATUS.get(payslip.status) or UNPAID_IN_RUN.get(run.status, "PENDING")
        batch.append(
            Payment(
                id=payslip.id,
                organization_id=run.organization_id,
                source_account_id=run.source_account_id,
                type="SALARY",
                worker_id=payslip.worker_id,
                pay_run_id=run.id,
                destination_account_number=payslip.worker.wallet.account_number,
                recipient_name=payslip.worker.wallet.owner.full_name,
                amount=payslip.amount,
                note=run.title,
                reference=payslip.transfer.reference if payslip.transfer_id else _reference(),
                status=status,
                created_by_id=run.created_by_id,
                transfer_id=payslip.transfer_id,
                reversal_id=payslip.reversal_id,
                reversed_by_id=payslip.reversed_by_id,
                reversed_at=payslip.reversed_at,
                reversal_reason=payslip.reversal_reason,
                idempotency_key=f"payslip-{payslip.id}",
                created_at=run.created_at,
                completed_at=run.paid_at if payslip.transfer_id else None,
            )
        )
        if len(batch) == 500:
            _save(Payment, batch)
            batch = []
    _save(Payment, batch)

    # Staff groups keep their access: the permissions follow the renamed model.
    for permission in Permission.objects.filter(
        content_type__app_label="organizations", codename__endswith="_paymentrequest"
    ):
        permission.codename = permission.codename.replace("_paymentrequest", "_payment")
        permission.name = permission.name.replace("payment request", "payment")
        permission.save(update_fields=["codename", "name"])


def _save(Payment, batch):
    if batch:
        created = Payment.objects.bulk_create(batch)
        # created_at is auto_now_add, so bulk_create set it to now; put back when the run was made.
        for payment, original in zip(created, batch, strict=True):
            payment.created_at = original.created_at
        Payment.objects.bulk_update(created, ["created_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0003_payment"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
