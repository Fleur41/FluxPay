"""Staff back-office (Django admin + Unfold): navigation, badges, environment label and the dashboard.

Everything here is read-only presentation; money still only moves through the services.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Sum
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.functional import lazy
from django.utils.html import format_html


def label(text: str, kind: str = "") -> str:
    """Unfold's coloured badge: kind is success, warning, danger, info or primary."""
    return render_to_string("unfold/helpers/label.html", {"text": text, "type": kind})


def _can_view(app_model: str):
    """Sidebar items show only to staff who may view that model."""
    app, model = app_model.split(".")
    return lambda request: (
        request.user.has_perm(f"{app}.view_{model}") or request.user.has_perm(f"{app}.change_{model}")
    )


def _item(title, icon, app_model, *, link=None, badge=None, permission=None):
    app, model = app_model.split(".")
    entry = {
        "title": title,
        "icon": icon,
        "link": link or reverse_lazy(f"admin:{app}_{model}_changelist"),
        "permission": permission or _can_view(app_model),
    }
    if badge:
        entry["badge"] = badge
    return entry


def sidebar_navigation(request):
    return [
        {
            "items": [
                {"title": "Dashboard", "icon": "space_dashboard", "link": reverse_lazy("admin:index")},
            ],
        },
        {
            "title": "Customers",
            "separator": True,
            "items": [
                _item("People", "person", "users.user"),
                _item("Wallets", "account_balance_wallet", "banking.account"),
            ],
        },
        {
            "title": "Money",
            "separator": True,
            "items": [
                _item(
                    "Top-ups & corrections",
                    "add_card",
                    "banking.manualadjustment",
                    permission=lambda r: (
                        r.user.has_perm("banking.post_adjustment") or r.user.has_perm("banking.view_manualadjustment")
                    ),
                ),
                _item("Transactions", "receipt_long", "banking.transaction"),
                _item("Transfers", "swap_horiz", "banking.transfer"),
            ],
        },
        {
            "title": "Accounting",
            "separator": True,
            "items": [
                _item(
                    "Cashbook",
                    "account_balance",
                    "accounting.cashbookentry",
                    badge="fluxpay.admin_site.badge_unallocated_receipts",
                    permission=lambda r: (
                        r.user.has_perm("accounting.record_cashbook")
                        or r.user.has_perm("accounting.view_cashbookentry")
                    ),
                ),
                {
                    "title": "Financial reports",
                    "icon": "monitoring",
                    "link": reverse_lazy("accounting_reports"),
                    "permission": lambda r: r.user.has_perm("accounting.view_financial_reports"),
                },
                {
                    "title": "Reconcile a bank account",
                    "icon": "fact_check",
                    "link": reverse_lazy("accounting_reconcile"),
                    "permission": lambda r: r.user.has_perm("accounting.reconcile_bank"),
                },
                _item("Journals", "menu_book", "accounting.journalentry"),
                _item("Chart of accounts", "account_tree", "accounting.ledgeraccount"),
                _item("Bank accounts", "account_balance_wallet", "accounting.bankaccount"),
                _item("Past reconciliations", "history", "accounting.bankreconciliation"),
            ],
        },
        {
            "title": "Businesses",
            "separator": True,
            "items": [
                _item(
                    "Onboard a business",
                    "add_business",
                    "organizations.organization",
                    link=reverse_lazy("admin:organizations_organization_onboard"),
                    permission=lambda r: r.user.has_perm("organizations.add_organization"),
                ),
                _item("Businesses", "storefront", "organizations.organization"),
                _item(
                    "Business payments",
                    "fact_check",
                    "organizations.payment",
                    badge="fluxpay.admin_site.badge_pending_approvals",
                ),
                _item("Beneficiaries", "contacts", "organizations.beneficiary"),
                _item("Invitations", "mail", "organizations.invitation"),
                _item("Pay runs", "payments", "payroll.payrun"),
                _item("Workers", "badge", "payroll.worker"),
                {
                    "title": "Business books",
                    "icon": "menu_book",
                    "link": reverse_lazy("accounting_business"),
                    "permission": lambda r: r.user.has_perm("accounting.view_financial_reports"),
                },
                _item("Business cashbooks", "receipt", "accounting.businessentry"),
                _item("Bills and invoices", "request_quote", "accounting.invoice"),
            ],
        },
        {
            "title": "External payments",
            "separator": True,
            "items": [
                _item(
                    "Payments", "payments", "payments.externalpayment", badge="fluxpay.admin_site.badge_needs_review"
                ),
                _item("Provider callbacks", "webhook", "payments.webhookevent"),
            ],
        },
        {
            "title": "Alerts & compliance",
            "separator": True,
            "items": [
                _item(
                    "Email & SMS alerts",
                    "notifications",
                    "notifications.notification",
                    badge="fluxpay.admin_site.badge_failed_alerts",
                ),
                _item("Audit log", "policy", "audit.auditevent"),
            ],
        },
        {
            "title": "Settings",
            "separator": True,
            "items": [
                _item(
                    "Platform rules",
                    "tune",
                    "platform_settings.platformsettings",
                    link=reverse_lazy("admin:platform_settings_platformsettings_change", args=[1]),
                ),
                _item("Currencies & limits", "currency_exchange", "platform_settings.currency"),
                _item(
                    "Accounting controls",
                    "lock_clock",
                    "accounting.accountingsettings",
                    link=reverse_lazy("admin:accounting_accountingsettings_change", args=[1]),
                ),
            ],
        },
        {
            "title": "Access",
            "separator": True,
            "items": [
                _item(
                    "Staff accounts",
                    "badge",
                    "users.user",
                    link=lazy(lambda: reverse("admin:users_user_changelist") + "?is_staff__exact=1", str)(),
                ),
                _item("Staff groups & permissions", "group", "auth.group"),
            ],
        },
    ]


def environment_callback(request):
    """The coloured label next to the site name, so staff always know which system they are in."""
    return ["Development", "warning"] if settings.DEBUG else ["Production", "danger"]


def _badge(count: int) -> str | None:
    return str(count) if count else None


def badge_pending_approvals(request):
    from organizations.models import Payment

    return _badge(Payment.objects.filter(status=Payment.Status.PENDING_APPROVAL).count())


def _open_receipts():
    from django.db.models import F

    from accounting.models import CashbookEntry

    return CashbookEntry.objects.filter(
        category=CashbookEntry.Category.CUSTOMER_DEPOSIT, reversed_by__isnull=True, allocated__lt=F("amount")
    )


def badge_unallocated_receipts(request):
    return _badge(_open_receipts().count())


def badge_needs_review(request):
    from payments.models import ExternalPayment

    return _badge(ExternalPayment.objects.filter(needs_review=True).count())


def badge_failed_alerts(request):
    from notifications.models import Notification

    return _badge(Notification.objects.filter(status=Notification.Status.FAILED).count())


def dashboard_callback(request, context):
    """Figures for the admin home page (templates/admin/index.html)."""
    from accounting import reports
    from audit.services import verify_chain
    from banking.models import Account, ManualAdjustment, Transaction, Transfer
    from notifications.models import Notification
    from organizations.models import Payment
    from payments.models import ExternalPayment
    from users.models import User

    now = timezone.now()
    today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    customers = User.objects.filter(is_active=True, is_staff=False).exclude(email__endswith="@fluxpay.internal")
    balances = (
        Account.objects.filter(system_key__isnull=True, is_active=True)
        .values("currency")
        .annotate(total=Sum("balance"), wallets=Count("id"))
        .order_by("-total")
    )
    transfers_today = Transfer.objects.filter(created_at__gte=today)
    volume_today = transfers_today.values("source__currency").annotate(total=Sum("amount")).order_by("-total")

    user = request.user
    can = {
        "balances": user.has_perm("banking.view_account"),
        "adjustments": user.has_perm("banking.post_adjustment") or user.has_perm("banking.view_manualadjustment"),
        "audit": user.has_perm("audit.view_auditevent"),
        "books": user.has_perm("accounting.view_financial_reports"),
    }
    # Each item links to a list; only show the ones this staff member can open.
    attention = [
        {
            "perm": "accounting.view_cashbookentry",
            "title": "Customer deposits waiting to be credited to a wallet",
            "count": _open_receipts().count(),
            "link": reverse("admin:accounting_cashbookentry_changelist") + "?allocation=open",
        },
        {
            "perm": "organizations.view_payment",
            "title": "Business payments waiting for approval",
            "count": Payment.objects.filter(status=Payment.Status.PENDING_APPROVAL).count(),
            "link": reverse("admin:organizations_payment_changelist") + "?status__exact=PENDING_APPROVAL",
        },
        {
            "perm": "payments.view_externalpayment",
            "title": "External payments needing review",
            "count": ExternalPayment.objects.filter(needs_review=True).count(),
            "link": reverse("admin:payments_externalpayment_changelist") + "?needs_review__exact=1",
        },
        {
            "perm": "payments.settle_payout",
            "title": "Bank payouts waiting to be sent by staff",
            "count": ExternalPayment.objects.filter(
                rail="BANK", direction="OUT", status__in=["HELD", "SUBMITTED"]
            ).count(),
            "link": reverse("admin:payments_externalpayment_changelist") + "?queue=bank",
        },
        {
            "perm": "notifications.view_notification",
            "title": "Alerts that failed to send",
            "count": Notification.objects.filter(status=Notification.Status.FAILED).count(),
            "link": reverse("admin:notifications_notification_changelist") + "?status__exact=FAILED",
        },
    ]
    allowed = {
        "accounting.view_cashbookentry": user.has_perm("accounting.view_cashbookentry")
        or user.has_perm("accounting.record_cashbook")
        or user.has_perm("banking.post_adjustment"),
    }
    attention = [item for item in attention if allowed.get(item["perm"], user.has_perm(item["perm"]))]
    for item in attention:
        item.pop("perm")
    broken_at = verify_chain() if can["audit"] else None

    if user.has_perm("organizations.view_organization"):
        context["businesses"] = business_overview()
        context["onboard_url"] = (
            reverse("admin:organizations_organization_onboard") if user.has_perm("organizations.add_organization") else ""
        )
        context["businesses_url"] = reverse("admin:organizations_organization_changelist")
    if can["audit"]:
        context["activity"] = activity_feed()
    context.update(
        {
            "kpis": [
                {
                    "title": "Active customers",
                    "value": f"{customers.count():,}",
                    "footer": f"{customers.filter(date_joined__gte=week_ago).count():,} joined in the last 7 days",
                },
                {
                    "title": "Transfers today",
                    "value": f"{transfers_today.count():,}",
                    "footer": ", ".join(f"{v['source__currency']} {v['total']:,.2f}" for v in volume_today)
                    or "No volume yet",
                },
                {
                    "title": "Top-ups today",
                    "value": f"{ManualAdjustment.objects.filter(created_at__gte=today).count():,}",
                    "footer": "Staff credits and corrections",
                },
                {
                    "title": "Failed transactions (7 days)",
                    "value": f"{Transaction.objects.filter(status='FAILED', created_at__gte=week_ago).count():,}",
                    "footer": "Held payouts that were returned",
                },
            ],
            "balances_table": {
                "headers": ["Currency", "Customer money held", "Wallets"],
                "rows": [[b["currency"], f"{b['total'] or Decimal('0'):,.2f}", f"{b['wallets']:,}"] for b in balances],
            },
            "attention": attention,
            "attention_total": sum(item["count"] for item in attention),
            "audit_ok": broken_at is None,
            "adjustments_table": {
                "headers": ["When", "Wallet", "Kind", "Amount", "By"],
                "rows": [
                    [
                        timezone.localtime(a.created_at).strftime("%d %b %H:%M"),
                        format_html(
                            '<a class="text-primary-600 dark:text-primary-500" href="{}">{}</a>',
                            reverse("admin:banking_manualadjustment_change", args=[a.pk]),
                            a.account.account_number,
                        ),
                        {
                            ManualAdjustment.Kind.CREDIT: label("Top-up", "success"),
                            ManualAdjustment.Kind.DEBIT: label("Correction", "warning"),
                            ManualAdjustment.Kind.PAYOUT: label("Cash withdrawal", "info"),
                        }[a.kind],
                        f"{a.account.currency} {a.amount:,.2f}",
                        a.created_by.full_name or a.created_by.email,
                    ]
                    for a in ManualAdjustment.objects.select_related("account", "created_by")[:6]
                ],
            },
            "greeting": _greeting(timezone.localtime(now).hour),
            "can": can,
            "can_post_adjustment": user.has_perm("banking.post_adjustment"),
            "can_record_cashbook": user.has_perm("accounting.record_cashbook"),
            "cashbook_add_url": reverse("admin:accounting_cashbookentry_add"),
            "reports_url": reverse("accounting_reports"),
            "safeguarding": [reports.safeguarding(c) for c in reports.currencies()] if can["books"] else [],
            "adjustment_add_url": reverse("admin:banking_manualadjustment_add"),
            "audit_url": reverse("admin:audit_auditevent_changelist"),
        }
    )
    return context


# What an audit action means, in a few words, for the activity feed (longest prefix wins).
ACTIVITY = {
    "org.onboarded": "Onboarded by FluxPay",
    "org.created": "Business started",
    "org.suspended": "Suspended by FluxPay",
    "org.reactivated": "Reactivated by FluxPay",
    "org.member.": "Team change",
    "org.invitation.": "Team invitation",
    "org.payment.": "Payment",
    "org.beneficiary.": "Supplier change",
    "org.settings_changed": "Settings changed",
    "payroll.": "Payroll",
    "worker.": "Workers",
    "books.": "Books",
    "adjustment.": "Wallet top-up / correction",
    "payment.": "M-Pesa / bank",
    "transfer.": "Transfer",
    "auth.": "Sign-in / security",
    "config.": "Platform settings",
}


def _activity(action: str) -> str:
    for prefix in sorted(ACTIVITY, key=len, reverse=True):
        if action.startswith(prefix):
            return ACTIVITY[prefix]
    return action


def business_overview(limit: int = 25) -> dict:
    """The god's-eye view of every business: money, payroll, what's owed, team, and when it last did anything."""
    from django.db.models import F, Max, Q

    from accounting.models import BusinessEntry, Invoice
    from accounting.services import business_date
    from banking.models import Account
    from organizations.models import Membership, Organization
    from payroll.models import Worker

    month_start = business_date().replace(day=1)
    organizations = list(Organization.objects.all())
    wallets = {a.organization_id: a for a in Account.objects.filter(organization__isnull=False).order_by("created_at")}
    month = {
        row["organization_id"]: row
        for row in BusinessEntry.objects.filter(date__gte=month_start).values("organization_id").annotate(
            money_in=Sum("amount", filter=Q(direction="IN")),
            money_out=Sum("amount", filter=Q(direction="OUT")),
            payroll=Sum("amount", filter=Q(source=BusinessEntry.Source.PAYROLL)),
        )
    }
    last = dict(BusinessEntry.objects.values("organization_id").annotate(last=Max("created_at")).values_list(
        "organization_id", "last"))  # fmt: skip
    workers = dict(Worker.objects.filter(status="ACTIVE").values("organization_id").annotate(n=Count("id")).values_list(
        "organization_id", "n"))  # fmt: skip
    owners = {}
    for m in Membership.objects.filter(role=Membership.Role.OWNER, is_active=True).select_related("user"):
        owners.setdefault(m.organization_id, m.user)
    owed = {}
    for row in (
        Invoice.objects.filter(status__in=(Invoice.Status.OPEN, Invoice.Status.PART_PAID))
        .values("organization_id", "kind").annotate(total=Sum(F("amount") - F("paid_amount")))
    ):  # fmt: skip
        owed[(row["organization_id"], row["kind"])] = row["total"]

    zero = Decimal("0")
    rows, totals, payroll_total = [], {}, zero
    for org in organizations:
        wallet = wallets.get(org.id)
        stats = month.get(org.id, {})
        if wallet:
            totals[wallet.currency] = totals.get(wallet.currency, zero) + wallet.balance
        payroll_total += stats.get("payroll") or zero
        rows.append({"org": org, "wallet": wallet, "stats": stats, "last": last.get(org.id), "owner": owners.get(org.id)})
    rows.sort(key=lambda r: (r["last"] is None, -(r["last"].timestamp() if r["last"] else 0)))

    def amount(value, currency):
        return f"{currency} {value or zero:,.2f}"

    table_rows = []
    for r in rows[:limit]:
        org, wallet, stats, currency = r["org"], r["wallet"], r["stats"], r["wallet"].currency if r["wallet"] else ""
        owner = r["owner"]
        table_rows.append([
            format_html('<a class="text-primary-600 dark:text-primary-500 font-medium" href="{}">{}</a>',
                        reverse("admin:organizations_organization_change", args=[org.pk]), org.name),
            format_html("{}<br><span class='text-xs'>{}</span>", owner.full_name, owner.email) if owner else "-",
            label("Active", "success") if org.status == "ACTIVE" else label("Suspended", "danger"),
            amount(wallet.balance, currency) if wallet else "-",
            f"{workers.get(org.id, 0):,}",
            amount(stats.get("payroll"), currency),
            amount(stats.get("money_in"), currency),
            amount(stats.get("money_out"), currency),
            format_html("{}<br><span class='text-xs'>owed to them {}</span>",
                        amount(owed.get((org.id, "BILL")), currency), amount(owed.get((org.id, "INVOICE")), currency)),
            timezone.localtime(r["last"]).strftime("%d %b %H:%M") if r["last"] else "No activity",
            format_html(
                '<a class="text-primary-600" href="{}?organization={}">Books</a> · '
                '<a class="text-primary-600" href="{}?organization={}">Logs</a>',
                reverse("accounting_business"), org.pk, reverse("admin:audit_auditevent_changelist"), org.pk,
            ),
        ])  # fmt: skip
    active = sum(1 for o in organizations if o.status == "ACTIVE")
    return {
        "kpis": [
            {"title": "Businesses", "value": f"{len(organizations):,}",
             "footer": f"{active:,} active, {len(organizations) - active:,} suspended"},
            {"title": "Money in business wallets", "value": ", ".join(f"{c} {v:,.0f}" for c, v in totals.items()) or "0",
             "footer": "Across every business cashbook"},
            {"title": "Payroll paid this month", "value": f"{payroll_total:,.0f}",
             "footer": f"Since {month_start:%d %b}, all businesses"},
            {"title": "Workers on payroll", "value": f"{sum(workers.values()):,}", "footer": "Active workers, all businesses"},
        ],
        "table": {
            "headers": ["Business", "Owner", "Status", "Wallet", "Workers", "Payroll (month)", "Money in (month)",
                        "Money out (month)", "They owe", "Last activity", ""],
            "rows": table_rows,
        },
        "more": max(len(rows) - limit, 0),
    }


def activity_feed(limit: int = 12) -> list[dict]:
    """The latest things that happened across FluxPay, newest first, with the business they concern."""
    from audit.models import AuditEvent
    from organizations.models import Organization

    events = list(AuditEvent.objects.order_by("-id")[:limit])
    names = dict(Organization.objects.filter(pk__in={e.organization_id for e in events if e.organization_id})
                 .values_list("pk", "name"))  # fmt: skip
    return [
        {
            "when": timezone.localtime(e.created_at).strftime("%d %b %H:%M"),
            "what": _activity(e.action),
            "action": e.action,
            "who": e.actor_label,
            "business": names.get(e.organization_id, ""),
            "link": reverse("admin:audit_auditevent_change", args=[e.pk]),
        }
        for e in events
    ]


def _greeting(hour: int) -> str:
    return "Good morning" if 5 <= hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
