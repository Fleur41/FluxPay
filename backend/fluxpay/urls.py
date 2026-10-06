from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from payments.views import WebhookView
from users.admin_mfa import staff_mfa

from . import web

admin.site.index_title = "Dashboard"  # header of the back-office home page


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/mfa/", staff_mfa, name="staff-mfa"),
    path("admin/accounting/reports/", include("accounting.urls_admin")),
    path("admin/", admin.site.urls),
    path("health/", health),
    # Pages that email and SMS links open (fluxpay/web.py). No trailing slash: they match the app's verified links.
    path("reset-password", web.reset_password, name="web-reset-password"),
    path("join", web.join, name="web-join"),
    path("join-business", web.join_business, name="web-join-business"),
    path("api/v1/auth/", include("users.urls")),
    path("api/v1/", include("banking.urls")),
    path("api/v1/", include("payments.urls")),
    path("api/v1/", include("organizations.urls")),
    path("api/v1/", include("payroll.urls")),
    path("api/v1/", include("notifications.urls")),
    path("api/v1/", include("platform_settings.urls")),
    # Provider callbacks: no JWT; guarded by the secret token and checked with the provider before use.
    path("hooks/<slug:rail>/<str:token>/", WebhookView.as_view(), name="payment-webhook"),
]
