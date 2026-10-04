from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from payments.views import WebhookView

admin.site.index_title = "Dashboard"  # header of the back-office home page


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
    path("api/v1/auth/", include("users.urls")),
    path("api/v1/", include("banking.urls")),
    path("api/v1/", include("payments.urls")),
    path("api/v1/", include("organizations.urls")),
    path("api/v1/", include("notifications.urls")),
    path("api/v1/", include("platform_settings.urls")),
    # Provider callbacks: no JWT; guarded by the secret token and checked with the provider before use.
    path("hooks/<slug:rail>/<str:token>/", WebhookView.as_view(), name="payment-webhook"),
]
