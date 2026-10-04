from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

from .services import record


@receiver(user_login_failed)
def record_failed_login(sender, credentials, request=None, **kwargs):
    # Django masks the password in `credentials`; only the attempted email is kept.
    email = str(credentials.get("email") or credentials.get("username") or "")[:254]
    record("auth.login_failed", metadata={"email": email.lower()})
