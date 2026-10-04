"""Payroll: the worker register, pay runs (with maker-checker approval) and reversing a wrong payment.

Permissions come from organizations.roles: owners, admins and finance prepare pay runs; owners and admins
approve them and reverse payments. Everything is audited in the same transaction.

Lock order: pay run row, then every wallet the run touches (all at once, by primary key), then
document numbers, then the audit chain head. Paying a run locks all its wallets up front so that 200
transfers in one transaction can't deadlock with a worker spending money at the same moment.
"""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction as db_transaction
from django.utils import timezone

from accounting import business as business_books
from accounting.models import BusinessEntry
from audit.services import record
from banking.models import Account
from banking.services import BOOKED_BY_CALLER, reverse_transfer, transfer_from_organization
from fluxpay.exceptions import BusinessError
from organizations.roles import Perm, has_perm
from platform_settings import services as rules
from users.models import User

from .models import PayRun, Payslip, Worker

S = PayRun.Status


def _require(membership, perm: Perm) -> None:
    if not has_perm(membership.role, perm):
        raise BusinessError("Your role doesn't allow this.", "permission_denied", 403)


def _business_wallet(organization, account_id=None) -> Account:
    wallets = Account.objects.filter(organization=organization, is_active=True)
    wallet = wallets.filter(id=account_id).first() if account_id else wallets.order_by("created_at").first()
    if wallet is None:
        raise BusinessError("Business wallet not found.", "account_not_found", 404)
    return wallet


# --- Workers ------------------------------------------------------------------------------------


def find_wallet(*, account_number: str = "", phone_number: str = "", currency: str) -> Account:
    """A worker's personal wallet, by its account number or the phone number they signed up with."""
    account_number, phone_number = (account_number or "").strip(), (phone_number or "").strip()
    personal = Account.objects.filter(
        system_key__isnull=True, organization__isnull=True, is_active=True
    ).select_related("owner")
    if account_number:
        wallet = personal.filter(account_number=account_number).first()
    elif phone_number:
        user = User.objects.filter(phone_number=phone_number, is_active=True).first()
        wallet = personal.filter(owner=user, currency=currency).order_by("created_at").first() if user else None
    else:
        raise BusinessError("Give the worker's FluxPay account number or phone number.", "worker_required")
    if wallet is None:
        raise BusinessError(
            "No FluxPay personal wallet found. The worker must sign up for FluxPay first.", "worker_not_found", 404
        )
    if wallet.currency != currency:
        raise BusinessError(f"The worker's wallet is in {wallet.currency}; payroll pays {currency}.", "currency_mismatch")
    return wallet


def _salary(value) -> Decimal:
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise BusinessError("Enter the salary as a number, e.g. 25000.", "invalid_salary") from None
    if amount <= 0:
        raise BusinessError("The salary must be more than zero.", "invalid_salary")
    return amount.quantize(Decimal("0.01"))


def add_worker(*, membership, account_number="", phone_number="", salary, employee_number="", job_title="",
               audit=True) -> tuple[Worker, bool]:  # fmt: skip
    """Adds a worker (or brings back one who left). Returns (worker, created)."""
    _require(membership, Perm.INITIATE_PAYMENT)
    organization = membership.organization
    payroll_wallet = _business_wallet(organization)
    wallet = find_wallet(account_number=account_number, phone_number=phone_number, currency=payroll_wallet.currency)
    salary = _salary(salary)
    worker, created = Worker.objects.get_or_create(
        organization=organization,
        wallet=wallet,
        defaults={
            "salary": salary,
            "employee_number": employee_number.strip()[:30],
            "job_title": job_title.strip()[:80],
            "added_by": membership.user,
        },
    )
    if not created:
        if worker.is_active and audit:
            raise BusinessError(f"{worker.name} is already on the payroll.", "already_worker")
        worker.salary, worker.is_active = salary, True
        worker.employee_number = employee_number.strip()[:30] or worker.employee_number
        worker.job_title = job_title.strip()[:80] or worker.job_title
        worker.save(update_fields=["salary", "is_active", "employee_number", "job_title", "updated_at"])
    if audit:
        record(
            "payroll.worker_added", actor=membership.user, organization_id=organization.id, target=worker,
            metadata={"name": worker.name, "account": wallet.account_number, "salary": str(salary)},
        )  # fmt: skip
    return worker, created


def import_workers(*, membership, rows: list[dict]) -> dict:
    """Adds many workers at once (e.g. from a spreadsheet). Good rows are saved; bad rows are reported back.

    Each row: account_number or phone_number, salary, and optionally employee_number and job_title.
    """
    _require(membership, Perm.INITIATE_PAYMENT)
    created = updated = 0
    errors = []
    with db_transaction.atomic():
        for number, row in enumerate(rows, start=1):
            try:
                with db_transaction.atomic():
                    _worker, was_created = add_worker(
                        membership=membership,
                        account_number=str(row.get("account_number") or ""),
                        phone_number=str(row.get("phone_number") or ""),
                        salary=row.get("salary"),
                        employee_number=str(row.get("employee_number") or ""),
                        job_title=str(row.get("job_title") or ""),
                        audit=False,
                    )
            except BusinessError as exc:
                errors.append({"row": number, "error": str(exc.detail)})
                continue
            created += was_created
            updated += not was_created
        record(
            "payroll.workers_imported", actor=membership.user, organization_id=membership.organization_id,
            target=membership.organization, metadata={"created": created, "updated": updated, "errors": len(errors)},
        )  # fmt: skip
    return {"created": created, "updated": updated, "errors": errors}


def update_worker(*, membership, worker_id, **changes) -> Worker:
    _require(membership, Perm.INITIATE_PAYMENT)
    with db_transaction.atomic():
        worker = _worker(membership, worker_id, lock=True)
        before = {}
        if "salary" in changes:
            changes["salary"] = _salary(changes["salary"])
        for field in ("salary", "job_title", "employee_number", "is_active"):
            if field in changes and getattr(worker, field) != changes[field]:
                before[field] = str(getattr(worker, field))
                setattr(worker, field, changes[field])
        if before:
            worker.save(update_fields=[*before, "updated_at"])
            record(
                "payroll.worker_changed" if worker.is_active else "payroll.worker_removed",
                actor=membership.user, organization_id=worker.organization_id, target=worker,
                metadata={"name": worker.name, "before": before, "after": {f: str(getattr(worker, f)) for f in before}},
            )  # fmt: skip
    return worker


def _worker(membership, worker_id, *, lock=False) -> Worker:
    workers = Worker.objects.select_related("wallet__owner").filter(organization_id=membership.organization_id)
    worker = (workers.select_for_update() if lock else workers).filter(id=worker_id).first()
    if worker is None:
        raise BusinessError("Worker not found.", "worker_not_found", 404)
    return worker


# --- Pay runs -----------------------------------------------------------------------------------


def create_pay_run(*, membership, title: str, pay_date, source_account_id=None, worker_ids=None) -> PayRun:
    """A draft pay run with a payslip for each chosen worker (all active workers if none are chosen),
    at their usual salary. Amounts can be changed while it is a draft."""
    _require(membership, Perm.INITIATE_PAYMENT)
    organization = membership.organization
    wallet = _business_wallet(organization, source_account_id)
    workers = Worker.objects.filter(organization=organization, is_active=True, wallet__currency=wallet.currency)
    if worker_ids:
        workers = workers.filter(id__in=worker_ids)
    workers = list(workers)
    if not workers:
        raise BusinessError("Add workers before creating a pay run.", "no_workers")
    with db_transaction.atomic():
        run = PayRun.objects.create(
            organization=organization, source_account=wallet, title=title.strip()[:80] or "Salaries",
            pay_date=pay_date, created_by=membership.user,
        )  # fmt: skip
        Payslip.objects.bulk_create(Payslip(pay_run=run, worker=w, amount=w.salary) for w in workers)
        record(
            "payroll.run_created", actor=membership.user, organization_id=organization.id, target=run,
            metadata={"title": run.title, "workers": len(workers), "total": str(total(run))},
        )  # fmt: skip
    return run


def total(run: PayRun, *, statuses=None) -> Decimal:
    from django.db.models import Sum

    payslips = run.payslips.all() if statuses is None else run.payslips.filter(status__in=statuses)
    return payslips.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")


def update_payslip(*, membership, run_id, payslip_id, amount=None, remove=False) -> PayRun:
    """Changes one worker's pay in a draft (e.g. overtime), or leaves them out of this run."""
    _require(membership, Perm.INITIATE_PAYMENT)
    with db_transaction.atomic():
        run = _run(membership, run_id, lock=True)
        if run.status != S.DRAFT:
            raise BusinessError("Only a draft pay run can be changed.", "not_draft")
        payslip = run.payslips.select_related("worker__wallet__owner").filter(id=payslip_id).first()
        if payslip is None:
            raise BusinessError("Payslip not found.", "payslip_not_found", 404)
        if remove:
            if run.payslips.count() == 1:
                raise BusinessError("A pay run needs at least one worker. Cancel it instead.", "last_payslip")
            payslip.delete()
        else:
            payslip.amount = _salary(amount)
            payslip.save(update_fields=["amount"])
    return run


def submit_pay_run(*, membership, run_id) -> PayRun:
    """Sends the pay run: paid straight away up to the approval threshold, otherwise waits for approval."""
    _require(membership, Perm.INITIATE_PAYMENT)
    with db_transaction.atomic():
        run = _run(membership, run_id, lock=True)
        if run.status != S.DRAFT:
            raise BusinessError("This pay run has already been sent.", "not_draft")
        amount = total(run)
        _check_funds(run, amount)
        run.submitted_at = timezone.now()
        if amount <= run.organization.approval_threshold:
            run.save(update_fields=["submitted_at", "updated_at"])
            _pay(run, actor=membership.user)
        else:
            run.status = S.PENDING_APPROVAL
            run.save(update_fields=["status", "submitted_at", "updated_at"])
            record(
                "payroll.run_submitted", actor=membership.user, organization_id=run.organization_id, target=run,
                metadata={"title": run.title, "total": str(amount), "workers": run.payslips.count()},
            )  # fmt: skip
    return run


def approve_pay_run(*, membership, run_id, note: str = "") -> PayRun:
    """A second person approves, and every worker is paid. Nobody can approve a run they prepared."""
    _require(membership, Perm.APPROVE_PAYMENT)
    with db_transaction.atomic():
        run = _run(membership, run_id, lock=True)
        if run.status != S.PENDING_APPROVAL:
            raise BusinessError("This pay run isn't waiting for approval.", "not_pending")
        if run.created_by_id == membership.user_id:
            raise BusinessError("You can't approve a pay run you prepared.", "self_approval", 403)
        run.decided_by, run.decided_at, run.decision_note = membership.user, timezone.now(), note[:255]
        run.save(update_fields=["decided_by", "decided_at", "decision_note", "updated_at"])
        _pay(run, actor=membership.user)
    return run


def reject_pay_run(*, membership, run_id, note: str = "") -> PayRun:
    _require(membership, Perm.APPROVE_PAYMENT)
    with db_transaction.atomic():
        run = _run(membership, run_id, lock=True)
        if run.status != S.PENDING_APPROVAL:
            raise BusinessError("This pay run isn't waiting for approval.", "not_pending")
        run.status, run.decided_by, run.decided_at, run.decision_note = S.REJECTED, membership.user, timezone.now(), note[:255]
        run.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
        record(
            "payroll.run_rejected", actor=membership.user, organization_id=run.organization_id, target=run,
            metadata={"title": run.title, "note": run.decision_note},
        )  # fmt: skip
    return run


def cancel_pay_run(*, membership, run_id) -> PayRun:
    _require(membership, Perm.INITIATE_PAYMENT)
    with db_transaction.atomic():
        run = _run(membership, run_id, lock=True)
        if run.status not in (S.DRAFT, S.PENDING_APPROVAL):
            raise BusinessError("A paid pay run can't be cancelled; reverse individual payments instead.", "not_cancellable")
        if run.status == S.PENDING_APPROVAL and run.created_by_id != membership.user_id:
            raise BusinessError("Only the person who prepared it can withdraw it; an approver can reject it.", "permission_denied", 403)
        run.status = S.CANCELLED
        run.save(update_fields=["status", "updated_at"])
        record("payroll.run_cancelled", actor=membership.user, organization_id=run.organization_id, target=run,
               metadata={"title": run.title})  # fmt: skip
    return run


def _check_funds(run: PayRun, amount: Decimal) -> None:
    wallet = Account.objects.get(id=run.source_account_id)
    if wallet.balance < amount:
        raise BusinessError(
            f"The business wallet holds {wallet.balance:,.2f} {wallet.currency}; this pay run needs "
            f"{amount:,.2f}. Add {amount - wallet.balance:,.2f} first.",
            "insufficient_funds",
        )


def _pay(run: PayRun, *, actor) -> None:
    """Pays every payslip, all or nothing, and writes one line in the business cashbook. Run row is locked."""
    payslips = list(run.payslips.select_related("worker__wallet__owner"))
    amount = sum((p.amount for p in payslips), Decimal("0.00"))
    # Every wallet first, in a fixed order, before anything takes the audit lock.
    ids = sorted({str(run.source_account_id), *(str(p.worker.wallet_id) for p in payslips)})
    list(Account.objects.select_for_update().filter(id__in=ids).order_by("id"))
    _check_funds(run, amount)
    for payslip in payslips:
        if not payslip.worker.wallet.is_active:
            raise BusinessError(f"{payslip.worker.name}'s wallet is closed. Remove them from this pay run.", "wallet_closed")
        transfer, _debit, _created = transfer_from_organization(
            initiator=actor,
            organization=run.organization,
            source_id=run.source_account_id,
            destination_number=payslip.worker.wallet.account_number,
            amount=payslip.amount,
            note=run.title,
            idempotency_key=f"payslip-{payslip.id}",
            books_role=BOOKED_BY_CALLER,
        )
        payslip.status, payslip.transfer = Payslip.Status.PAID, transfer
    Payslip.objects.bulk_update(payslips, ["status", "transfer"])
    wallet = Account.objects.select_related("organization").get(id=run.source_account_id)
    run.book_entry = business_books.record_movement(
        wallet=wallet, direction="OUT", amount=amount, source=BusinessEntry.Source.PAYROLL,
        reference=f"PAYRUN-{str(run.id)[:8].upper()}", counterparty=f"{len(payslips)} workers",
        description=f"{run.title} · {len(payslips)} workers", role="salaries", actor=actor,
    )  # fmt: skip
    run.status, run.paid_at = S.PAID, timezone.now()
    run.save(update_fields=["status", "paid_at", "book_entry", "updated_at"])
    record(
        "payroll.run_paid", actor=actor, organization_id=run.organization_id, target=run,
        metadata={"title": run.title, "workers": len(payslips), "total": str(amount), "currency": wallet.currency},
    )  # fmt: skip


def reverse_payslip(*, membership, payslip_id, reason: str) -> Payslip:
    """Takes back a salary paid in error, while the worker still holds it and within the platform's window."""
    _require(membership, Perm.APPROVE_PAYMENT)
    with db_transaction.atomic():
        payslip = (
            Payslip.objects.select_for_update(of=("self",))
            .select_related("pay_run", "worker__wallet__owner", "transfer")
            .filter(id=payslip_id, pay_run__organization_id=membership.organization_id)
            .first()
        )
        if payslip is None:
            raise BusinessError("Payslip not found.", "payslip_not_found", 404)
        if payslip.status != Payslip.Status.PAID:
            raise BusinessError("Only a paid payslip can be reversed.", "not_paid")
        days = rules.platform().payroll_reversal_days
        if timezone.now() - payslip.pay_run.paid_at > timedelta(days=days):
            raise BusinessError(
                f"Payments can only be reversed within {days} days of payday. Ask {payslip.worker.name} to send it back.",
                "reversal_window_passed",
            )
        booked = {}

        def book(reversal):
            booked["entry"] = business_books.record_movement(
                wallet=reversal.destination, direction="IN", amount=reversal.amount,
                source=BusinessEntry.Source.PAYROLL_REVERSAL, reference=reversal.reference,
                counterparty=payslip.worker.name, counterparty_account=payslip.worker.wallet.account_number,
                description=f"Reversed {payslip.pay_run.title} pay: {reason}"[:255], role="salaries",
                actor=membership.user,
            )  # fmt: skip

        reversal = reverse_transfer(
            transfer=payslip.transfer, initiator=membership.user, reason=reason, books_role=BOOKED_BY_CALLER, book=book
        )
        payslip.status, payslip.reversal = Payslip.Status.REVERSED, reversal
        payslip.reversed_by, payslip.reversed_at, payslip.reversal_reason = membership.user, timezone.now(), reason[:255]
        payslip.save(update_fields=["status", "reversal", "reversed_by", "reversed_at", "reversal_reason"])
        record(
            "payroll.payslip_reversed", actor=membership.user, organization_id=membership.organization_id,
            target=payslip,
            metadata={"worker": payslip.worker.name, "amount": str(payslip.amount), "reason": reason,
                      "reference": reversal.reference},
        )  # fmt: skip
    return payslip


def _run(membership, run_id, *, lock=False) -> PayRun:
    runs = PayRun.objects.select_related("organization").filter(organization_id=membership.organization_id)
    run = (runs.select_for_update(of=("self",)) if lock else runs).filter(id=run_id).first()
    if run is None:
        raise BusinessError("Pay run not found.", "pay_run_not_found", 404)
    return run

