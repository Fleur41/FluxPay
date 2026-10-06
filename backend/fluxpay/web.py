"""The few public web pages that email and SMS links open (FLUXPAY_WEB_URL).

Email apps don't open app-only links (fluxpay://...), so every link is an ordinary web link to one of these:

    /reset-password?uid=...&token=...   choose a new password right here, in the browser
    /join?code=...                      a worker's invitation: the code, and "Open in the FluxPay app"
    /join-business?token=...            an invitation to a business's team: "Open in the FluxPay app"

They hold no session and show nothing about an account beyond what the link itself proves.
"""

from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.shortcuts import render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from audit.services import record

User = get_user_model()


def _app_link(host: str, **params) -> str:
    return f"fluxpay://{host}?{urlencode(params)}"


def _reset_user(uid: str, token: str):
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return None
    return user if default_token_generator.check_token(user, token) else None


@never_cache
@require_http_methods(["GET", "POST"])
def reset_password(request):
    from django.contrib.auth import password_validation
    from django.core.exceptions import ValidationError

    uid, token = request.GET.get("uid", ""), request.GET.get("token", "")
    user = _reset_user(uid, token)
    context = {"app_link": _app_link("reset-password", uid=uid, token=token), "errors": []}
    if user is None:
        return render(request, "web/reset_password.html", {**context, "invalid": True}, status=400)
    if request.method == "POST":
        password, again = request.POST.get("password", ""), request.POST.get("password_again", "")
        if password != again:
            context["errors"] = ["The two passwords don't match."]
        else:
            try:
                password_validation.validate_password(password, user=user)
            except ValidationError as exc:
                context["errors"] = list(exc.messages)
        if not context["errors"]:
            with transaction.atomic():
                user.set_password(password)
                user.save(update_fields=["password"])
                record("auth.password_reset", actor=user, metadata={"via": "web"})
            return render(request, "web/reset_password.html", {**context, "done": True, "email": user.email})
    return render(request, "web/reset_password.html", {**context, "email": user.email})


@never_cache
def join(request):
    """A worker's invitation code. Nothing is looked up: the app checks the code when it's entered."""
    code = request.GET.get("code", "").strip()[:20]
    shown = f"{code[:5]}-{code[5:]}" if len(code) == 10 and "-" not in code else code
    return render(request, "web/join.html", {"code": shown, "app_link": _app_link("join-employer", code=code)})


@never_cache
def join_business(request):
    """An invitation to a business's team. The token is only checked when it's accepted in the app."""
    token = request.GET.get("token", "").strip()[:100]
    return render(request, "web/join_business.html", {
        "token": token, "app_link": _app_link("join-business", token=token), "page_link": request.build_absolute_uri(),
    })  # fmt: skip
