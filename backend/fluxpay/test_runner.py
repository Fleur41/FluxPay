import os

from django.conf import settings
from django.test.runner import DiscoverRunner

OFF = {"FLUXPAY_REQUIRE_STAFF_MFA": False, "FLUXPAY_REQUIRE_BUSINESS_MFA": False}


class FluxPayTestRunner(DiscoverRunner):
    """Most tests act as owners, admins and staff without setting up an authenticator app, so two-step
    verification is switched off for them; the tests about it switch it on with override_settings."""

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        for name, value in OFF.items():
            setattr(settings, name, value)
            os.environ[name] = str(value)  # parallel workers start fresh and read their settings from here
