"""
FluxPay backend settings.

All environment-specific values are read from environment variables so the
same code runs locally (dev), on staging and in production.
"""
import base64
import hashlib
import os
from datetime import timedelta
from pathlib import Path

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
    "users.middleware.StaffMfaMiddleware",
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
# FluxPay runs on East Africa Time: the admin, logs, business dates and Celery all show Nairobi time.
# The database still stores exact moments (USE_TZ), so changing this never changes saved data.
TIME_ZONE = os.environ.get("TIME_ZONE", "Africa/Nairobi")
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
        "worker_codes": "30/hour",  # entering invitation and join codes
        "mfa": "10/min",  # two-step verification codes at sign-in
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

# Email (alerts, invitations, password resets). Printed to the log until an SMTP server is set: then sent for real.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", EMAIL_PORT == 587)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", EMAIL_PORT == 465)
EMAIL_TIMEOUT = 20
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    # Real SMTP, but test addresses (*.test, example.com...) are only printed, so seed data doesn't bounce.
    "notifications.email.SmtpExceptTestAddressesBackend" if EMAIL_HOST else "django.core.mail.backends.console.EmailBackend",
)
# Most providers only accept mail "from" the account you sign in with (e.g. your Gmail address).
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", f"FluxPay <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "FluxPay <no-reply@fluxpay.app>"
)
# Links in emails and SMS are ordinary web links to this server (fluxpay/web.py), so they open anywhere: a page
# that resets the password in the browser, or shows the invitation code with an "Open in the FluxPay app" button.
# In development, http://localhost:8000 also works on a phone connected with `adb reverse tcp:8000 tcp:8000`.
FLUXPAY_WEB_URL = os.environ.get("FLUXPAY_WEB_URL", "http://localhost:8000" if DEBUG else "https://fluxpay.app").rstrip("/")
PASSWORD_RESET_LINK = os.environ.get("PASSWORD_RESET_LINK", FLUXPAY_WEB_URL + "/reset-password?uid={uid}&token={token}")
# Team invitations (admin, finance, viewer).
ORG_INVITE_LINK = os.environ.get("ORG_INVITE_LINK", FLUXPAY_WEB_URL + "/join-business?token={token}")
# Workers: a personal invitation (SMS/email), and a business's join code (shown as a QR code the app scans).
WORKER_INVITE_LINK = os.environ.get("WORKER_INVITE_LINK", FLUXPAY_WEB_URL + "/join?code={code}")
WORKER_JOIN_LINK = os.environ.get("WORKER_JOIN_LINK", "fluxpay://join-employer?business={code}")

# Two-step verification (users.mfa). The key encrypts authenticator secrets: a Fernet key
# (python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"). Set it in production;
# without it one is derived from DJANGO_SECRET_KEY, and changing that key would then turn everyone's codes off.
FLUXPAY_MFA_KEY = os.environ.get("FLUXPAY_MFA_KEY") or base64.urlsafe_b64encode(
    hashlib.sha256(f"fluxpay-mfa:{SECRET_KEY}".encode()).digest()
).decode()
# Staff must pass two-step verification before using the back office; business owners and admins before
# doing anything with a business beyond looking at it.
FLUXPAY_REQUIRE_STAFF_MFA = env_bool("FLUXPAY_REQUIRE_STAFF_MFA", True)
FLUXPAY_REQUIRE_BUSINESS_MFA = env_bool("FLUXPAY_REQUIRE_BUSINESS_MFA", True)
TEST_RUNNER = "fluxpay.test_runner.FluxPayTestRunner"

# External payments (payments app)
# Rail -> provider adapter class. A rail is enabled below once it is configured; the fake one exists only in tests.
FLUXPAY_PAYMENT_PROVIDERS = {}
# Public https base URL of this API; payment providers send callbacks to it.
FLUXPAY_PUBLIC_URL = os.environ.get("FLUXPAY_PUBLIC_URL", "")
# Secret path segment in every callback URL (/hooks/<rail>/<token>/). Empty disables all callbacks.
FLUXPAY_WEBHOOK_TOKEN = os.environ.get("FLUXPAY_WEBHOOK_TOKEN", "dev-webhook-token" if DEBUG else "")
FLUXPAY_STATUS_CHECK_AFTER_SECONDS = int(os.environ.get("FLUXPAY_STATUS_CHECK_AFTER_SECONDS", "120"))
FLUXPAY_DEPOSIT_EXPIRY_MINUTES = int(os.environ.get("FLUXPAY_DEPOSIT_EXPIRY_MINUTES", "30"))
# A payout with no outcome after this long is flagged for staff to check (it is never failed on silence).
FLUXPAY_PAYOUT_REVIEW_AFTER_HOURS = int(os.environ.get("FLUXPAY_PAYOUT_REVIEW_AFTER_HOURS", "24"))
FLUXPAY_WEBHOOK_MATCH_RETRIES = 5

# M-Pesa (Safaricom Daraja). STK Push deposits need the consumer key/secret, passkey and a public URL;
# payouts (B2C to phones, B2B to paybills and tills) also need an initiator and its security credential
# (the initiator password encrypted with Safaricom's certificate, as the Daraja portal generates it).
MPESA_ENV = os.environ.get("MPESA_ENV", "sandbox")
if MPESA_ENV not in {"sandbox", "production"}:
    raise RuntimeError("MPESA_ENV must be 'sandbox' or 'production'")
MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY", "")
MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET", "")
MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE", "174379")  # Daraja's sandbox test Paybill
MPESA_PASSKEY = os.environ.get("MPESA_PASSKEY", "")
MPESA_PAYOUT_SHORTCODE = os.environ.get("MPESA_PAYOUT_SHORTCODE", "") or MPESA_SHORTCODE
MPESA_INITIATOR_NAME = os.environ.get("MPESA_INITIATOR_NAME", "")
MPESA_SECURITY_CREDENTIAL = os.environ.get("MPESA_SECURITY_CREDENTIAL", "")
if all((MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, MPESA_PASSKEY, FLUXPAY_PUBLIC_URL)):
    FLUXPAY_PAYMENT_PROVIDERS["MPESA"] = "payments.providers.mpesa.MpesaProvider"
elif DEBUG and env_bool("FLUXPAY_FAKE_MPESA", True):
    # Local development without Daraja keys: M-Pesa deposits and withdrawals are accepted and succeed at the
    # next status check (resolve-stuck-payments), so the whole flow can be tried. Never with DEBUG off.
    FLUXPAY_PAYMENT_PROVIDERS["MPESA"] = "payments.providers.fake.FakeProvider"
# Bank payouts are sent by FluxPay staff from the bank and confirmed in the admin (there is no bank API).
# Only switch this on when someone works the queue.
if env_bool("FLUXPAY_BANK_PAYOUTS", DEBUG):
    FLUXPAY_PAYMENT_PROVIDERS["BANK"] = "payments.providers.bank.ManualBankProvider"
# Transaction alerts (notifications app). Times in alerts and statements are shown in this zone.
FLUXPAY_DISPLAY_TIMEZONE = os.environ.get("FLUXPAY_DISPLAY_TIMEZONE", TIME_ZONE)
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
