"""The back office's second step: staff set up two-step verification once, then enter a code each session."""

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils.http import url_has_allowed_host_and_scheme

from audit.services import record
from fluxpay.exceptions import BusinessError

from . import mfa
from .middleware import SESSION_KEY


@login_required(login_url="/admin/login/")
def staff_mfa(request):
    user = request.user
    if not user.is_staff:
        return HttpResponseRedirect("/admin/login/")
    next_url = request.POST.get("next") or request.GET.get("next") or "/admin/"
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = "/admin/"
    context = {**admin.site.each_context(request), "title": "Two-step verification", "next": next_url, "error": None}
    setting_up = not user.mfa_enabled

    if request.method == "POST":
        try:
            if setting_up:
                context["recovery_codes"] = mfa.enable(user, request.POST.get("code", ""))
            else:
                mfa.check(user, request.POST.get("code", ""))
        except BusinessError as exc:
            context["error"] = str(exc.detail)
        else:
            request.session[SESSION_KEY] = str(user.pk)
            record("auth.staff_mfa_passed", actor=user)
            if "recovery_codes" in context:  # shown once, before going on
                return TemplateResponse(request, "users/staff_mfa.html", context)
            return HttpResponseRedirect(next_url)

    if setting_up:
        user.refresh_from_db()
        if not user.mfa_pending_secret or request.method == "GET":
            context["secret"], context["otpauth_uri"] = mfa.begin_setup(user)
        else:
            secret = mfa.decrypt(user.mfa_pending_secret)
            context["secret"], context["otpauth_uri"] = secret, mfa.otpauth_uri(user.email, secret)
        context["secret_groups"] = " ".join(context["secret"][i:i + 4] for i in range(0, len(context["secret"]), 4))
    context["setting_up"] = setting_up
    return TemplateResponse(request, "users/staff_mfa.html", context)
