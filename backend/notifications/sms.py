"""SMS delivery. FLUXPAY_SMS_BACKEND picks the backend; the console one just logs (like Django's console email)."""
import logging
import re

import requests
from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class SmsError(Exception):
    """The message could not be sent. Delivery is retried, then marked failed."""


class ConsoleSmsBackend:
    def send(self, to: str, message: str) -> str:
        logger.info("SMS to %s: %s", to, message)
        print(f"[SMS to {to}] {message}", flush=True)  # visible in `docker compose logs`, like console email
        return "console"


class AfricasTalkingSmsBackend:
    """Africa's Talking bulk SMS API. Set AFRICASTALKING_USERNAME ("sandbox" for testing) and _API_KEY."""

    URLS = {
        "sandbox": "https://api.sandbox.africastalking.com/version1/messaging",
        "production": "https://api.africastalking.com/version1/messaging",
    }

    def send(self, to: str, message: str) -> str:
        username = settings.AFRICASTALKING_USERNAME
        data = {"username": username, "to": to, "message": message}
        if settings.AFRICASTALKING_SENDER_ID:
            data["from"] = settings.AFRICASTALKING_SENDER_ID
        url = self.URLS["sandbox" if username == "sandbox" else "production"]
        try:
            response = requests.post(
                url,
                data=data,
                headers={"apiKey": settings.AFRICASTALKING_API_KEY, "Accept": "application/json"},
                timeout=(5, 20),
            )
            response.raise_for_status()
            recipients = response.json()["SMSMessageData"]["Recipients"]
        except (requests.RequestException, ValueError, KeyError) as exc:
            raise SmsError(f"Africa's Talking request failed: {exc}") from exc
        if not recipients or recipients[0].get("status") != "Success":
            status = recipients[0].get("status") if recipients else "no recipients"
            raise SmsError(f"Africa's Talking did not accept the message: {status}")
        return str(recipients[0].get("messageId", ""))


def get_sms_backend():
    return import_string(settings.FLUXPAY_SMS_BACKEND)()


def normalize_phone(raw: str) -> str | None:
    """Returns an E.164 number (+254712345678), or None when `raw` is not a usable phone number.

    Kenyan local formats (0712..., 712..., 254712...) are converted; other numbers must start with +.
    """
    digits = re.sub(r"[\s()-]", "", raw or "")
    if digits.startswith("+"):
        return digits if re.fullmatch(r"\+[1-9]\d{7,14}", digits) else None
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif len(digits) == 9:
        digits = "254" + digits
    return f"+{digits}" if re.fullmatch(r"254[17]\d{8}", digits) else None
