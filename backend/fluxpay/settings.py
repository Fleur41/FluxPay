"""
FluxPay backend settings.

All environment-specific values are read from environment variables so the
same code runs locally (dev), on staging and in production.
"""
from datetime import timedelta
from pathlib import Path
import os

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-change-me-before-deploying-fluxpay" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off")

# 10.0.2.2 is the host loopback as seen from the Android emulator.
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,10.0.2.2")

INSTALLED_APPS = [
    # Unfold styles the staff back-office; it must come before django.contrib.admin.
    "unfold",
    "unfold.contrib.filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    # Local
    "users",
    "banking",
    "payments",
    "organizations",
    "audit",
    "notifications",
    "platform_settings",
    "accounting",
    "payroll",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves collected static files (admin styles) from gunicorn, with caching and compression.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "audit.middleware.AuditContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "fluxpay.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # admin/index.html: the back-office dashboard
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "fluxpay.wsgi.application"

# PostgreSQL in every real environment, e.g.
#   DATABASE_URL=postgres://fluxpay:fluxpay@localhost:5432/fluxpay
# SQLite is only a zero-setup fallback for quick local runs and tests.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Hashed file names + gzip/brotli, so browsers can cache styles forever and still get updates.
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "COERCE_DECIMAL_TO_STRING": True,
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/min",
        "user": "300/min",
        "transfers": "20/min",
        "deposits": "10/min",
        "statements": "10/min",
    },
    "EXCEPTION_HANDLER": "fluxpay.exceptions.api_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")

# Email (password reset links). Console backend prints emails in dev.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "FluxPay <no-reply@fluxpay.app>")
# Deep link the Android app opens (handled by MainActivity).
PASSWORD_RESET_LINK = os.environ.get("PASSWORD_RESET_LINK", "fluxpay://reset-password?uid={uid}&token={token}")
# Deep link in business invitation emails.
ORG_INVITE_LINK = os.environ.get("ORG_INVITE_LINK", "fluxpay://join-business?token={token}")

# External payments (payments app)
# Rail -> provider adapter class. No rail is enabled yet; the fake provider exists only in tests.
FLUXPAY_PAYMENT_PROVIDERS = {}
# Secret path segment in every callback URL (/hooks/<rail>/<token>/). Empty disables all callbacks.
FLUXPAY_WEBHOOK_TOKEN = os.environ.get("FLUXPAY_WEBHOOK_TOKEN", "dev-webhook-token" if DEBUG else "")
FLUXPAY_STATUS_CHECK_AFTER_SECONDS = int(os.environ.get("FLUXPAY_STATUS_CHECK_AFTER_SECONDS", "120"))
FLUXPAY_DEPOSIT_EXPIRY_MINUTES = int(os.environ.get("FLUXPAY_DEPOSIT_EXPIRY_MINUTES", "30"))
FLUXPAY_WEBHOOK_MATCH_RETRIES = 5
# Transaction alerts (notifications app). Times in alerts and statements are shown in this zone.
FLUXPAY_DISPLAY_TIMEZONE = os.environ.get("FLUXPAY_DISPLAY_TIMEZONE", "Africa/Nairobi")
# SMS: Africa's Talking once an API key is set, otherwise printed to the log.
AFRICASTALKING_USERNAME = os.environ.get("AFRICASTALKING_USERNAME", "sandbox")
AFRICASTALKING_API_KEY = os.environ.get("AFRICASTALKING_API_KEY", "")
AFRICASTALKING_SENDER_ID = os.environ.get("AFRICASTALKING_SENDER_ID", "")
FLUXPAY_SMS_BACKEND = os.environ.get(
    "FLUXPAY_SMS_BACKEND",
    "notifications.sms.AfricasTalkingSmsBackend" if AFRICASTALKING_API_KEY else "notifications.sms.ConsoleSmsBackend",
)

# Celery (background payment work). Without a broker, tasks run inline in the web process,
# which keeps `manage.py runserver` working with no Redis; scheduled jobs then don't run.
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "")
CELERY_TASK_ALWAYS_EAGER = not CELERY_BROKER_URL
CELERY_TASK_ACKS_LATE = True  # a job is re-run if its worker dies mid-way; every task is idempotent
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "resolve-stuck-payments": {"task": "payments.tasks.resolve_stuck_payments", "schedule": 300.0},
    "expire-abandoned-deposits": {"task": "payments.tasks.expire_abandoned_deposits", "schedule": 900.0},
}

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Staff back-office (Django admin themed by Unfold). Navigation and dashboard live in fluxpay/admin_site.py.
UNFOLD = {
    "SITE_TITLE": "FluxPay Admin",
    "SITE_HEADER": "FluxPay",
    "SITE_SUBHEADER": "Back-office",
    "SITE_SYMBOL": "account_balance_wallet",
    "SITE_URL": None,
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
    "ENVIRONMENT": "fluxpay.admin_site.environment_callback",
    "DASHBOARD_CALLBACK": "fluxpay.admin_site.dashboard_callback",
    "COMMAND": {"search_models": True},  # Cmd/Ctrl+K jumps to any screen
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": "fluxpay.admin_site.sidebar_navigation",
    },
    # FluxPay brand purple (the app's #4F3BD8), as an OKLCH scale.
    "COLORS": {
        "primary": {
            "50": "oklch(97% .016 280)",
            "100": "oklch(94% .035 280)",
            "200": "oklch(88% .07 280)",
            "300": "oklch(79% .12 279)",
            "400": "oklch(67% .19 277)",
            "500": "oklch(57% .23 275)",
            "600": "oklch(50% .24 273)",
            "700": "oklch(44% .22 273)",
            "800": "oklch(37% .18 274)",
            "900": "oklch(31% .14 275)",
            "950": "oklch(22% .1 276)",
        },
    },
}
