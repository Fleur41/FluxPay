from urllib.parse import quote

from django.conf import settings
from django.shortcuts import redirect

SESSION_KEY = "mfa_verified_user"
# Reachable before the second step: signing in and out, and the two-step page itself.
OPEN_PATHS = ("/admin/login/", "/admin/logout/", "/admin/mfa/", "/admin/jsi18n/")


class StaffMfaMiddleware:
    """Staff pass two-step verification once per back-office session before any admin page opens.

    The admin's own login checks the password; this sends a signed-in staff member to /admin/mfa/ (to set it up
    the first time, then to enter a code) until this session has passed the second step.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            settings.FLUXPAY_REQUIRE_STAFF_MFA
            and request.path.startswith("/admin/")
            and not request.path.startswith(OPEN_PATHS)
            and user is not None
            and user.is_authenticated
            and user.is_staff
            and request.session.get(SESSION_KEY) != str(user.pk)
        ):
            return redirect(f"/admin/mfa/?next={quote(request.get_full_path())}")
        return self.get_response(request)
