"""Two-step verification: a 6-digit code from an authenticator app (TOTP, RFC 6238) on top of the password.

Required for FluxPay staff in the back office, and for business owners and admins to do anything with a business
beyond looking (organizations.services.membership_for). Anyone may turn it on for their own account.

- The secret is stored encrypted (Fernet, FLUXPAY_MFA_KEY); a database leak alone doesn't give away codes.
- Each code works once: the last accepted time step is kept, so a code seen over someone's shoulder can't be
  replayed. Codes from one step either side of now are accepted, for phone clocks that drift.
- Ten recovery codes are given when it's turned on, for a lost phone; each works once and only its hash is stored.
- After 5 wrong codes, codes are refused for 15 minutes.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db import transaction as db_transaction
from django.utils import timezone

from audit.services import record
from fluxpay.exceptions import BusinessError

DIGITS = 6
STEP = 30  # seconds
DRIFT = 1  # steps accepted either side of now
RECOVERY_CODES = 10
MAX_FAILURES, LOCKOUT_SECONDS = 5, 15 * 60
CHALLENGE_SALT, CHALLENGE_SECONDS = "fluxpay.mfa-login", 5 * 60


# --- TOTP ---------------------------------------------------------------------------------------


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 10**DIGITS
    return f"{value:0{DIGITS}d}"


def current_counter(now: float | None = None) -> int:
    return int((now if now is not None else time.time()) // STEP)


def otpauth_uri(email: str, secret: str) -> str:
    """What authenticator apps import (as a QR code or a link)."""
    return (f"otpauth://totp/FluxPay:{quote(email)}?secret={secret}&issuer=FluxPay"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP}")  # fmt: skip


# --- Secrets at rest ----------------------------------------------------------------------------


def _fernet() -> Fernet:
    return Fernet(settings.FLUXPAY_MFA_KEY)


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise BusinessError("Two-step verification can't be checked right now. Contact support.", "mfa_unavailable") from None


# --- Who needs it -------------------------------------------------------------------------------


def is_required(user) -> bool:
    """Staff, and anyone who is an owner or admin of a business."""
    from organizations.models import Membership

    return user.is_staff or Membership.objects.filter(
        user=user, is_active=True, role__in=[Membership.Role.OWNER, Membership.Role.ADMIN]
    ).exists()


# --- Turning it on and off ----------------------------------------------------------------------


def begin_setup(user) -> tuple[str, str]:
    """A new secret for the user's authenticator app, kept aside until they confirm it with a code."""
    secret = new_secret()
    user.mfa_pending_secret = encrypt(secret)
    user.save(update_fields=["mfa_pending_secret"])
    return secret, otpauth_uri(user.email, secret)


def enable(user, code: str) -> list[str]:
    """Confirms the pending secret with a code from the app. Returns the recovery codes, shown only this once."""
    from .models import MfaRecoveryCode, User

    with db_transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        if not user.mfa_pending_secret:
            raise BusinessError("Start the setup first.", "mfa_not_started")
        counter = _match(decrypt(user.mfa_pending_secret), code, after=0)
        if counter is None:
            _failed(user)
            raise BusinessError("That code isn't right. Check the time on your phone and try again.", "mfa_invalid_code")
        user.mfa_secret, user.mfa_pending_secret = user.mfa_pending_secret, ""
        user.mfa_enabled_at, user.mfa_last_counter = timezone.now(), counter
        user.save(update_fields=["mfa_secret", "mfa_pending_secret", "mfa_enabled_at", "mfa_last_counter"])
        codes = _new_recovery_codes(user, MfaRecoveryCode)
        record("auth.mfa_enabled", actor=user, target=user)
    return codes


def disable(user, password: str, code: str) -> None:
    from .models import MfaRecoveryCode, User

    if not user.check_password(password or ""):
        raise BusinessError("Your password isn't right.", "invalid_password", 403)
    check(user, code)
    with db_transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        user.mfa_secret, user.mfa_pending_secret, user.mfa_enabled_at = "", "", None
        user.save(update_fields=["mfa_secret", "mfa_pending_secret", "mfa_enabled_at"])
        MfaRecoveryCode.objects.filter(user=user).delete()
        record("auth.mfa_disabled", actor=user, target=user)


def new_recovery_codes(user, code: str) -> list[str]:
    """Replaces the recovery codes (the old ones stop working). Needs a current code."""
    from .models import MfaRecoveryCode

    check(user, code)
    with db_transaction.atomic():
        codes = _new_recovery_codes(user, MfaRecoveryCode)
        record("auth.mfa_recovery_codes_replaced", actor=user, target=user)
    return codes


# --- Checking a code ----------------------------------------------------------------------------


def check(user, code: str) -> None:
    """Accepts a current authenticator code or an unused recovery code, once. Raises BusinessError otherwise."""
    from .models import MfaRecoveryCode, User

    if cache.get(_lock_key(user)):
        raise BusinessError("Too many wrong codes. Try again in 15 minutes.", "mfa_locked", 429)
    code = "".join(ch for ch in (code or "") if ch.isalnum()).upper()
    with db_transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        if not user.mfa_enabled_at:
            raise BusinessError("Two-step verification isn't on for this account.", "mfa_not_enabled")
        if len(code) == DIGITS and code.isdigit():
            counter = _match(decrypt(user.mfa_secret), code, after=user.mfa_last_counter)
            if counter is not None:
                user.mfa_last_counter = counter
                user.save(update_fields=["mfa_last_counter"])
                cache.delete(_failures_key(user))
                return
        else:
            recovery = MfaRecoveryCode.objects.filter(user=user, code_hash=_hash(code), used_at__isnull=True).first()
            if recovery is not None:
                recovery.used_at = timezone.now()
                recovery.save(update_fields=["used_at"])
                record("auth.mfa_recovery_code_used", actor=user, target=user,
                       metadata={"left": MfaRecoveryCode.objects.filter(user=user, used_at__isnull=True).count()})
                cache.delete(_failures_key(user))
                return
    _failed(user)
    raise BusinessError("That code isn't right.", "mfa_invalid_code", 400)


def _match(secret: str, code: str, *, after: int) -> int | None:
    """The time step `code` belongs to, if it's within the drift window and newer than `after`."""
    now = current_counter()
    for counter in range(now - DRIFT, now + DRIFT + 1):
        if counter > after and hmac.compare_digest(code_at(secret, counter), code or ""):
            return counter
    return None


def _failed(user) -> None:
    key = _failures_key(user)
    failures = cache.get(key, 0) + 1
    cache.set(key, failures, LOCKOUT_SECONDS)
    if failures >= MAX_FAILURES:
        cache.set(_lock_key(user), True, LOCKOUT_SECONDS)
        cache.delete(key)
        record("auth.mfa_locked", actor=user, target=user)


def _failures_key(user) -> str:
    return f"mfa:failures:{user.pk}"


def _lock_key(user) -> str:
    return f"mfa:locked:{user.pk}"


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _new_recovery_codes(user, MfaRecoveryCode) -> list[str]:
    MfaRecoveryCode.objects.filter(user=user).delete()
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    codes = ["".join(secrets.choice(alphabet) for _ in range(10)) for _ in range(RECOVERY_CODES)]
    MfaRecoveryCode.objects.bulk_create(MfaRecoveryCode(user=user, code_hash=_hash(c)) for c in codes)
    return [f"{c[:5]}-{c[5:]}" for c in codes]


# --- The login challenge ------------------------------------------------------------------------


def challenge_for(user) -> str:
    """A short-lived token proving the password was right; exchanged with a code for the real tokens.

    It carries part of the password hash, so it stops working if the password changes in the meantime.
    """
    return signing.dumps({"u": str(user.pk), "p": user.password[-16:]}, salt=CHALLENGE_SALT)


def user_from_challenge(token: str):
    from .models import User

    try:
        data = signing.loads(token or "", salt=CHALLENGE_SALT, max_age=CHALLENGE_SECONDS)
    except signing.BadSignature:
        raise BusinessError("Your sign-in expired. Enter your password again.", "mfa_challenge_expired", 401) from None
    user = User.objects.filter(pk=data.get("u"), is_active=True).first()
    if user is None or user.password[-16:] != data.get("p"):
        raise BusinessError("Your sign-in expired. Enter your password again.", "mfa_challenge_expired", 401)
    return user
