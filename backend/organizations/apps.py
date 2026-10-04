from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "organizations"

    def ready(self):
        # Connects services.on_payout_settled, which finishes business payments sent by M-Pesa or bank,
        # in every process that settles payments (web and Celery workers alike).
        from . import services  # noqa: F401
