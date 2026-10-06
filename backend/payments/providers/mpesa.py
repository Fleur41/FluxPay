"""M-Pesa through Safaricom's Daraja API: STK Push deposits, and payouts to phones (B2C), paybills and tills (B2B).

Deposits: start_deposit sends an STK Push (the customer's phone shows a PIN prompt) -> Daraja calls our
callback when the customer answers -> we confirm with STK Push Query before crediting.

Payouts: start_payout sends a B2C or B2B request -> Daraja answers with a ConversationID straight away and
posts the outcome to our result URL later. Daraja has no synchronous status API for these (Transaction
Status Query answers by callback too), so the outcome comes from that result callback, which we accept
only for a ConversationID Daraja gave us and for the exact amount. With no result, a payout is never
failed: it stays SUBMITTED and is flagged for staff after FLUXPAY_PAYOUT_REVIEW_AFTER_HOURS.

Daraja may not de-duplicate a payout request that is sent twice, so payouts are not idempotent here:
payments.services never resubmits one whose first attempt went unanswered; staff check it instead.
"""

import base64
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
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
# B2B: paying a paybill or a till. Both identify the parties by shortcode (identifier type 4).
B2B_COMMANDS = {"MPESA_PAYBILL": "BusinessPayBill", "MPESA_TILL": "BusinessBuyGoods"}


class DarajaRejected(ProviderError):
    """Daraja refused the request (bad phone number, invalid amount, ...). No money moved."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{message or 'Rejected by M-Pesa'} ({code})")
        self.code = code


class MpesaProvider(PaymentProvider):
    currencies = frozenset({"KES"})
    whole_units_only = True  # Daraja takes whole shillings
    payouts_idempotent = False

    @classmethod
    def can_pay_out(cls) -> bool:
        return bool(settings.MPESA_INITIATOR_NAME and settings.MPESA_SECURITY_CREDENTIAL)

    def start_deposit(self, payment) -> SubmitResult:
        timestamp = self._timestamp()
        body = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": self._password(timestamp),
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(payment.amount),
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
        if not self.can_pay_out():
            raise ProviderError("M-Pesa payouts aren't set up on this server.")
        meta = payment.metadata
        remarks = (meta.get("remarks") or f"FluxPay {payment.reference}")[:100]
        common = {
            "SecurityCredential": settings.MPESA_SECURITY_CREDENTIAL,
            "Amount": int(payment.amount),
            "PartyA": settings.MPESA_PAYOUT_SHORTCODE,
            "Remarks": remarks if len(remarks) >= 2 else "FluxPay",
            "QueueTimeOutURL": callback_url(),
            "ResultURL": callback_url(),
        }
        if payment.method == "MPESA_B2C":
            body = {
                **common,
                "OriginatorConversationID": payment.reference,
                "InitiatorName": settings.MPESA_INITIATOR_NAME,
                "CommandID": "BusinessPayment",
                "PartyB": meta["mpesa_phone"].removeprefix("+"),
                "Occasion": payment.reference,
            }
            data = self._post("/mpesa/b2c/v3/paymentrequest", body)
        elif payment.method in B2B_COMMANDS:
            till = payment.method == "MPESA_TILL"
            body = {
                **common,
                "Initiator": settings.MPESA_INITIATOR_NAME,
                "CommandID": B2B_COMMANDS[payment.method],
                "SenderIdentifierType": "4",
                "RecieverIdentifierType": "4",  # sic: Daraja's spelling
                "PartyB": meta["till_number"] if till else meta["paybill_number"],
                "AccountReference": payment.reference if till else meta["paybill_account"],
            }
            data = self._post("/mpesa/b2b/v1/paymentrequest", body)
        else:
            raise ProviderError(f"M-Pesa can't send a {payment.get_method_display()}.")
        if str(data.get("ResponseCode")) != "0" or not data.get("ConversationID"):
            raise ProviderError(data.get("ResponseDescription") or "M-Pesa rejected the payout")
        return SubmitResult(
            provider_ref=data["ConversationID"],
            metadata={"originator_conversation_id": data.get("OriginatorConversationID", "")},
        )

    def fetch_status(self, payment) -> StatusResult:
        if payment.direction == "OUT":
            return self._payout_status(payment)
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
        if isinstance(payload.get("Body"), dict):
            return self._stk_callback(payload)
        if isinstance(payload.get("Result"), dict):
            return self._result_callback(payload["Result"])
        raise InvalidCallback("Not an M-Pesa callback.")

    # --- Callbacks ---

    @staticmethod
    def _stk_callback(payload: dict) -> Callback:
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
                details["provider_receipt"] = str(item["Value"])[:32]
        # Daraja sends one result per checkout, so its id doubles as the event id.
        return Callback(event_id=checkout_id, provider_ref=checkout_id, details=details)

    @staticmethod
    def _result_callback(result: dict) -> Callback:
        """A B2C or B2B outcome. Kept on the payment as `mpesa_result`, which fetch_status then reads."""
        conversation_id = result.get("ConversationID")
        if not isinstance(conversation_id, str) or not conversation_id or "ResultCode" not in result:
            raise InvalidCallback("M-Pesa result has no ConversationID or ResultCode.")
        parameters = (result.get("ResultParameters") or {}).get("ResultParameter") or []
        if isinstance(parameters, dict):  # Daraja sends a single parameter as an object, not a list
            parameters = [parameters]
        values = {p.get("Key"): p.get("Value") for p in parameters if isinstance(p, dict)}
        amount = values.get("TransactionAmount", values.get("Amount"))
        outcome = {
            "code": str(result["ResultCode"]),
            "description": str(result.get("ResultDesc", ""))[:255],
            "originator": str(result.get("OriginatorConversationID", "")),
            "amount": str(amount) if amount is not None else "",
            "receipt": str(result.get("TransactionID") or values.get("TransactionReceipt") or "")[:32],
            "recipient": str(values.get("ReceiverPartyPublicName", ""))[:150],
        }
        details = {"mpesa_result": outcome}
        if outcome["receipt"]:
            details["provider_receipt"] = outcome["receipt"]
        return Callback(event_id=f"result:{conversation_id}", provider_ref=conversation_id, details=details)

    @staticmethod
    def _payout_status(payment) -> StatusResult:
        outcome = payment.metadata.get("mpesa_result")
        if not outcome:
            return StatusResult(state=ProviderState.UNKNOWN)  # no result yet: never a failure
        if outcome.get("originator") not in ("", payment.reference, payment.metadata.get("originator_conversation_id")):
            logger.warning("M-Pesa result for %s names another request: %s", payment.reference, outcome)
            return StatusResult(state=ProviderState.UNKNOWN)
        if outcome.get("code") != "0":
            return StatusResult(state=ProviderState.FAILED, reason=outcome.get("description") or "M-Pesa payout failed")
        try:
            amount = Decimal(outcome["amount"]) if outcome.get("amount") else None
        except InvalidOperation:
            amount = None
        # A success must state its amount: complete_payment holds the payment for review if it differs.
        if amount is None:
            return StatusResult(state=ProviderState.UNKNOWN)
        return StatusResult(
            state=ProviderState.SUCCEEDED, amount=amount, currency="KES", provider_ref=payment.provider_ref
        )

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
