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
            "title": "Businesses",
            "separator": True,
            "items": [
                _item("Businesses", "storefront", "organizations.organization"),
                _item(
                    "Payment approvals",
                    "fact_check",
                    "organizations.paymentrequest",
                    badge="fluxpay.admin_site.badge_pending_approvals",
                ),
                _item("Invitations", "mail", "organizations.invitation"),
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
                _item("Staff groups", "group", "auth.group"),
            ],
        },
    ]


def environment_callback(request):
    """The coloured label next to the site name, so staff always know which system they are in."""
    return ["Development", "warning"] if settings.DEBUG else ["Production", "danger"]


def _badge(count: int) -> str | None:
    return str(count) if count else None


def badge_pending_approvals(request):
    from organizations.models import PaymentRequest

    return _badge(PaymentRequest.objects.filter(status=PaymentRequest.Status.PENDING_APPROVAL).count())


def badge_needs_review(request):
    from payments.models import ExternalPayment

    return _badge(ExternalPayment.objects.filter(needs_review=True).count())


def badge_failed_alerts(request):
    from notifications.models import Notification

    return _badge(Notification.objects.filter(status=Notification.Status.FAILED).count())


def dashboard_callback(request, context):
    """Figures for the admin home page (templates/admin/index.html)."""
    from audit.services import verify_chain
    from banking.models import Account, ManualAdjustment, Transaction, Transfer
    from notifications.models import Notification
    from organizations.models import PaymentRequest
    from payments.models import ExternalPayment
    from users.models import User

    now = timezone.now()
    today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    customers = User.objects.filter(is_active=True).exclude(email__endswith="@fluxpay.internal")
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
    }
    # Each item links to a list; only show the ones this staff member can open.
    attention = [
        {
            "perm": "organizations.view_paymentrequest",
            "title": "Business payments waiting for approval",
            "count": PaymentRequest.objects.filter(status=PaymentRequest.Status.PENDING_APPROVAL).count(),
            "link": reverse("admin:organizations_paymentrequest_changelist") + "?status__exact=PENDING_APPROVAL",
        },
        {
            "perm": "payments.view_externalpayment",
            "title": "External payments needing review",
            "count": ExternalPayment.objects.filter(needs_review=True).count(),
            "link": reverse("admin:payments_externalpayment_changelist") + "?needs_review__exact=1",
        },
        {
            "perm": "notifications.view_notification",
            "title": "Alerts that failed to send",
            "count": Notification.objects.filter(status=Notification.Status.FAILED).count(),
            "link": reverse("admin:notifications_notification_changelist") + "?status__exact=FAILED",
        },
    ]
    attention = [item for item in attention if user.has_perm(item.pop("perm"))]
    broken_at = verify_chain() if can["audit"] else None

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
                        label("Top-up", "success")
                        if a.kind == ManualAdjustment.Kind.CREDIT
                        else label("Correction", "warning"),
                        f"{a.account.currency} {a.amount:,.2f}",
                        a.created_by.full_name or a.created_by.email,
                    ]
                    for a in ManualAdjustment.objects.select_related("account", "created_by")[:6]
                ],
            },
            "greeting": _greeting(timezone.localtime(now).hour),
            "can": can,
            "can_post_adjustment": user.has_perm("banking.post_adjustment"),
            "adjustment_add_url": reverse("admin:banking_manualadjustment_add"),
            "audit_url": reverse("admin:audit_auditevent_changelist"),
        }
    )
    return context


def _greeting(hour: int) -> str:
    return "Good morning" if 5 <= hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
