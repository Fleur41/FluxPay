"""M-Pesa through Safaricom's Daraja API. This milestone covers STK Push deposits only.

Flow: start_deposit sends an STK Push (the customer's phone shows a PIN prompt) -> Daraja calls our
callback when the customer answers -> we confirm with STK Push Query before crediting.
"""
import base64
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core.cache import cache

from .base import (
    Callback,
    InvalidCallback,
    PaymentProvider,
    ProviderError,
    ProviderState,
    ProviderUnavailable,
    StatusResult,
    SubmitResult,
)

logger = logging.getLogger(__name__)

BASE_URLS = {"sandbox": "https://sandbox.safaricom.co.ke", "production": "https://api.safaricom.co.ke"}
NAIROBI = ZoneInfo("Africa/Nairobi")  # Daraja timestamps are in Kenyan time
TIMEOUT = (5, 30)  # connect, read (seconds)
# STK Push Query answers this while the customer has not responded yet.
STILL_PROCESSING = "500.001.1001"
# Daraja answers this (HTTP 404) for an expired token, or one from an app without access to the API.
INVALID_TOKEN = "404.001.03"
TOKEN_CACHE_KEY = "payments:mpesa:access-token"


class DarajaRejected(ProviderError):
    """Daraja refused the request (bad phone number, invalid amount, ...). No money moved."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{message or 'Rejected by M-Pesa'} ({code})")
        self.code = code


class MpesaProvider(PaymentProvider):
    def start_deposit(self, payment) -> SubmitResult:
        timestamp = self._timestamp()
        body = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": self._password(timestamp),
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(payment.amount),  # Daraja takes whole shillings; the API layer rejects cents
            "PartyA": payment.metadata["phone_number"],
            "PartyB": settings.MPESA_SHORTCODE,
            "PhoneNumber": payment.metadata["phone_number"],
            "CallBackURL": callback_url(),
            "AccountReference": payment.account.account_number,  # shown on the customer's prompt (max 12)
            "TransactionDesc": "FluxPay",  # max 13 characters
        }
        data = self._post("/mpesa/stkpush/v1/processrequest", body)
        if data.get("ResponseCode") != "0" or not data.get("CheckoutRequestID"):
            raise ProviderError(data.get("ResponseDescription") or data.get("errorMessage") or "STK Push rejected")
        return SubmitResult(
            provider_ref=data["CheckoutRequestID"], metadata={"merchant_request_id": data.get("MerchantRequestID", "")}
        )

    def start_payout(self, payment) -> SubmitResult:
        raise ProviderError("M-Pesa payouts (B2C) are not available yet.")

    def fetch_status(self, payment) -> StatusResult:
        if not payment.provider_ref:
            # STK Push Query needs the CheckoutRequestID; without it there is nothing to ask about.
            return StatusResult(state=ProviderState.UNKNOWN)
        timestamp = self._timestamp()
        body = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": self._password(timestamp),
            "Timestamp": timestamp,
            "CheckoutRequestID": payment.provider_ref,
        }
        try:
            data = self._post("/mpesa/stkpushquery/v1/query", body)
        except DarajaRejected as exc:
            if exc.code == STILL_PROCESSING:
                return StatusResult(state=ProviderState.PENDING)
            raise ProviderUnavailable(f"STK Push Query failed: {exc}") from exc

        result_code = str(data.get("ResultCode", ""))
        if result_code == "0":
            # The query does not return the amount; the callback's amount is not trusted on its own.
            return StatusResult(state=ProviderState.SUCCEEDED, provider_ref=payment.provider_ref)
        if result_code:
            # 1032 cancelled by the customer, 1037 no response, 1 insufficient funds, 2001 wrong PIN, ...
            return StatusResult(state=ProviderState.FAILED, reason=data.get("ResultDesc", "M-Pesa payment failed"))
        return StatusResult(state=ProviderState.UNKNOWN)

    def parse_callback(self, headers: dict, payload: dict) -> Callback:
        try:
            stk = payload["Body"]["stkCallback"]
            checkout_id = stk["CheckoutRequestID"]
        except (KeyError, TypeError):
            raise InvalidCallback("Not an M-Pesa STK Push callback.") from None
        if not isinstance(checkout_id, str) or not checkout_id:
            raise InvalidCallback("Callback has no CheckoutRequestID.")

        details = {}
        items = (stk.get("CallbackMetadata") or {}).get("Item") or []
        for item in items:
            if isinstance(item, dict) and item.get("Name") == "MpesaReceiptNumber" and item.get("Value"):
                details["mpesa_receipt"] = str(item["Value"])[:32]
        # Daraja sends one result per checkout, so its id doubles as the event id.
        return Callback(event_id=checkout_id, provider_ref=checkout_id, details=details)

    # --- Daraja plumbing ---

    def _post(self, path: str, body: dict) -> dict:
        """POSTs to Daraja. Raises ProviderError for a definite rejection, ProviderUnavailable otherwise."""
        try:
            response = requests.post(
                base_url() + path,
                json=body,
                headers={"Authorization": f"Bearer {self._token()}"},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise ProviderUnavailable(f"Daraja unreachable: {exc}") from exc

        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code == 401 or data.get("errorCode") == INVALID_TOKEN:
            # Our credentials problem, not the customer's: drop the token and retry with a fresh one.
            # If it keeps happening, the Daraja app is likely not enabled for this API (e.g. M-Pesa Express).
            cache.delete(TOKEN_CACHE_KEY)
            logger.warning("Daraja rejected the access token on %s: %s", path, data)
            raise ProviderUnavailable("Daraja rejected the access token.")
        if response.status_code >= 500 and data.get("errorCode") != STILL_PROCESSING:
            raise ProviderUnavailable(f"Daraja error {response.status_code}: {data.get('errorMessage', '')}")
        if response.status_code >= 400 or data.get("errorCode"):
            logger.info("Daraja rejected %s: %s", path, data)
            raise DarajaRejected(data.get("errorCode") or f"HTTP {response.status_code}", data.get("errorMessage", ""))
        return data

    def _token(self) -> str:
        token = cache.get(TOKEN_CACHE_KEY)
        if token:
            return token
        try:
            response = requests.get(
                base_url() + "/oauth/v1/generate",
                params={"grant_type": "client_credentials"},
                auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderUnavailable(f"Could not get a Daraja access token: {exc}") from exc
        token = data["access_token"]
        # Daraja tokens last an hour; refresh a minute early.
        cache.set(TOKEN_CACHE_KEY, token, max(int(data.get("expires_in", 3599)) - 60, 60))
        return token

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(NAIROBI).strftime("%Y%m%d%H%M%S")

    @staticmethod
    def _password(timestamp: str) -> str:
        raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
        return base64.b64encode(raw.encode()).decode()


def base_url() -> str:
    return BASE_URLS[settings.MPESA_ENV]


def callback_url() -> str:
    return f"{settings.FLUXPAY_PUBLIC_URL.rstrip('/')}/hooks/mpesa/{settings.FLUXPAY_WEBHOOK_TOKEN}/"
