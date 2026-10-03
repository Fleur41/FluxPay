"""M-Pesa STK Push adapter, with Daraja's HTTP calls mocked using its documented payload shapes."""
import base64
from decimal import Decimal
from unittest import mock

import requests
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from banking.services import open_wallet

from . import services
from .models import ExternalPayment
from .providers.base import ProviderUnavailable
from .tests import FAKE, TOKEN, PaymentTestMixin

Status = ExternalPayment.Status
PUBLIC_URL = "https://fluxpay-test.example.com"
mpesa_settings = override_settings(
    FLUXPAY_SIGNUP_BONUS=Decimal("1000.00"),
    FLUXPAY_PAYMENT_PROVIDERS={**FAKE, "MPESA": "payments.providers.mpesa.MpesaProvider"},
    FLUXPAY_WEBHOOK_TOKEN=TOKEN,
    FLUXPAY_PUBLIC_URL=PUBLIC_URL,
    MPESA_ENV="sandbox",
    MPESA_CONSUMER_KEY="test-key",
    MPESA_CONSUMER_SECRET="test-secret",
    MPESA_SHORTCODE="174379",
    MPESA_PASSKEY="test-passkey",
)

CHECKOUT_ID = "ws_CO_191220191020363925"


def http(status_code=200, json=None):
    response = mock.Mock(status_code=status_code)
    response.json.return_value = json if json is not None else {}
    response.raise_for_status.side_effect = None if status_code < 400 else requests.HTTPError(str(status_code))
    return response


TOKEN_RESPONSE = http(json={"access_token": "daraja-token", "expires_in": "3599"})
STK_ACCEPTED = http(
    json={
        "MerchantRequestID": "29115-34620561-1",
        "CheckoutRequestID": CHECKOUT_ID,
        "ResponseCode": "0",
        "ResponseDescription": "Success. Request accepted for processing",
        "CustomerMessage": "Success. Request accepted for processing",
    }
)


def query_result(code: str, desc: str):
    return http(json={"ResponseCode": "0", "ResultCode": code, "ResultDesc": desc, "CheckoutRequestID": CHECKOUT_ID})


def stk_callback(result_code=0, receipt="NLJ7RT61SV"):
    stk = {
        "MerchantRequestID": "29115-34620561-1",
        "CheckoutRequestID": CHECKOUT_ID,
        "ResultCode": result_code,
        "ResultDesc": "The service request is processed successfully.",
    }
    if result_code == 0:
        stk["CallbackMetadata"] = {
            "Item": [
                {"Name": "Amount", "Value": 100.00},
                {"Name": "MpesaReceiptNumber", "Value": receipt},
                {"Name": "TransactionDate", "Value": 20191219102115},
                {"Name": "PhoneNumber", "Value": 254712345678},
            ]
        }
    return {"Body": {"stkCallback": stk}}


@mpesa_settings
@mock.patch("payments.providers.mpesa.requests.get", return_value=TOKEN_RESPONSE)
@mock.patch("payments.providers.mpesa.requests.post")
class MpesaDepositTests(PaymentTestMixin, APITestCase):
    def setUp(self):
        cache.clear()  # the Daraja access token is cached
        self.user, self.wallet = self.make_user()
        self.client.force_authenticate(self.user)

    def request_deposit(self, phone="0712 345 678", amount="100", key="mpesa-key-001"):
        with self.after_commit():
            return self.client.post(
                "/api/v1/deposits/mpesa/",
                {"account_id": str(self.wallet.id), "phone_number": phone, "amount": amount, "idempotency_key": key},
                format="json",
            )

    def send_callback(self, payload):
        with self.after_commit():
            return self.client.post(f"/hooks/mpesa/{TOKEN}/", payload, format="json")

    def test_sends_stk_push_and_waits(self, post, get):
        post.return_value = STK_ACCEPTED
        res = self.request_deposit()
        self.assertEqual(res.status_code, 202, res.data)
        self.assertEqual(self.balance(self.wallet), Decimal("1000.00"))

        payment = ExternalPayment.objects.get()
        self.assertEqual(payment.status, Status.PENDING)
        self.assertEqual(payment.provider_ref, CHECKOUT_ID)
        self.assertEqual(payment.metadata["phone_number"], "254712345678")

        url = post.call_args.args[0]
        body = post.call_args.kwargs["json"]
        self.assertEqual(url, "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer daraja-token")
        self.assertEqual(body["Amount"], 100)
        self.assertEqual(body["PartyA"], "254712345678")
        self.assertEqual(body["PhoneNumber"], "254712345678")
        self.assertEqual(body["PartyB"], "174379")
        self.assertEqual(body["TransactionType"], "CustomerPayBillOnline")
        self.assertEqual(body["AccountReference"], self.wallet.account_number)
        self.assertEqual(body["CallBackURL"], f"{PUBLIC_URL}/hooks/mpesa/{TOKEN}/")
        self.assertEqual(len(body["Timestamp"]), 14)
        self.assertEqual(
            base64.b64decode(body["Password"]).decode(), "174379" + "test-passkey" + body["Timestamp"]
        )
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs["auth"], ("test-key", "test-secret"))

    def test_confirmed_payment_credits_wallet_and_keeps_receipt(self, post, get):
        post.return_value = STK_ACCEPTED
        self.request_deposit()
        post.return_value = query_result("0", "The service request is processed successfully.")

        res = self.send_callback(stk_callback())
        self.assertEqual(res.status_code, 200, res.data)
        payment = ExternalPayment.objects.get()
        self.assertEqual(payment.status, Status.COMPLETED)
        self.assertEqual(payment.metadata["mpesa_receipt"], "NLJ7RT61SV")
        self.assertEqual(self.balance(self.wallet), Decimal("1100.00"))
        self.assertTrue(post.call_args.args[0].endswith("/mpesa/stkpushquery/v1/query"))
        self.assertEqual(post.call_args.kwargs["json"]["CheckoutRequestID"], CHECKOUT_ID)
        self.assertLedgerBalanced()

    def test_customer_cancelling_fails_deposit(self, post, get):
        post.return_value = STK_ACCEPTED
        self.request_deposit()
        post.return_value = query_result("1032", "Request cancelled by user")
        self.send_callback(stk_callback(result_code=1032))
        payment = ExternalPayment.objects.get()
        self.assertEqual(payment.status, Status.FAILED)
        self.assertEqual(payment.failure_reason, "Request cancelled by user")
        self.assertEqual(self.balance(self.wallet), Decimal("1000.00"))

    def test_forged_success_callback_is_overruled_by_query(self, post, get):
        post.return_value = STK_ACCEPTED
        self.request_deposit()
        post.return_value = query_result("1037", "DS timeout user cannot be reached")
        self.send_callback(stk_callback(result_code=0))  # claims success
        self.assertEqual(ExternalPayment.objects.get().status, Status.FAILED)
        self.assertEqual(self.balance(self.wallet), Decimal("1000.00"))

    def test_still_processing_leaves_deposit_pending(self, post, get):
        post.return_value = STK_ACCEPTED
        self.request_deposit()
        post.return_value = http(
            500, {"requestId": "1", "errorCode": "500.001.1001", "errorMessage": "The transaction is being processed"}
        )
        payment = services.check_with_provider(ExternalPayment.objects.get().id)
        self.assertEqual(payment.status, Status.PENDING)

    def test_daraja_rejecting_the_request_fails_deposit_with_reason(self, post, get):
        post.return_value = http(
            400, {"requestId": "1", "errorCode": "400.002.02", "errorMessage": "Bad Request - Invalid PhoneNumber"}
        )
        res = self.request_deposit()
        self.assertEqual(res.status_code, 202)
        payment = ExternalPayment.objects.get()
        self.assertEqual(payment.status, Status.FAILED)
        self.assertEqual(payment.failure_reason, "Bad Request - Invalid PhoneNumber (400.002.02)")

    def test_daraja_unreachable_keeps_deposit_for_retry(self, post, get):
        post.side_effect = requests.ConnectionError("connection refused")
        payment, _ = services.start_deposit(  # on_commit work is not run here
            user=self.user,
            account_id=self.wallet.id,
            rail="MPESA",
            method=ExternalPayment.Method.STK,
            amount=Decimal("100"),
            idempotency_key="retry-key-001",
            metadata={"phone_number": "254712345678"},
        )
        with self.assertRaises(ProviderUnavailable):
            services.submit_payment(payment.id)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Status.CREATED)

    def test_invalid_access_token_retries_instead_of_failing(self, post, get):
        # The exact response Daraja's sandbox gave in live testing (HTTP 404).
        post.return_value = http(
            404, {"requestId": "", "errorCode": "404.001.03", "errorMessage": "Invalid Access Token"}
        )
        payment, _ = services.start_deposit(  # on_commit work is not run here
            user=self.user,
            account_id=self.wallet.id,
            rail="MPESA",
            method=ExternalPayment.Method.STK,
            amount=Decimal("1"),
            idempotency_key="bad-token-001",
            metadata={"phone_number": "254712345678"},
        )
        with self.assertRaises(ProviderUnavailable):
            services.submit_payment(payment.id)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Status.CREATED)  # kept for the retry, not failed

        post.return_value = STK_ACCEPTED
        payment = services.submit_payment(payment.id)
        self.assertEqual(payment.status, Status.PENDING)
        self.assertEqual(get.call_count, 2)  # the rejected token was dropped and a new one fetched

    def test_access_token_is_reused(self, post, get):
        post.return_value = STK_ACCEPTED
        self.request_deposit(key="mpesa-key-001")
        post.return_value = http(json={**STK_ACCEPTED.json(), "CheckoutRequestID": "ws_CO_second"})
        self.request_deposit(key="mpesa-key-002")
        get.assert_called_once()

    def test_rejects_bad_phone_numbers_and_cents(self, post, get):
        for phone in ("0812345678", "12345", "+1 202 555 0100"):
            res = self.request_deposit(phone=phone)
            self.assertEqual(res.status_code, 400, phone)
            self.assertEqual(res.data["error"]["code"], "validation_error")
        res = self.request_deposit(amount="100.50")
        self.assertEqual(res.status_code, 400)
        self.assertIn("whole shillings", res.data["error"]["message"])
        post.assert_not_called()

    def test_accepts_common_phone_formats(self, post, get):
        post.return_value = STK_ACCEPTED
        for i, phone in enumerate(("0712345678", "712345678", "+254712345678", "254712345678", "0112345678")):
            ExternalPayment.objects.all().delete()
            res = self.request_deposit(phone=phone, key=f"format-key-{i:03}")
            self.assertEqual(res.status_code, 202, phone)
        self.assertEqual(ExternalPayment.objects.get().metadata["phone_number"], "254112345678")

    def test_usd_wallet_is_refused(self, post, get):
        self.wallet = open_wallet(self.user, currency="USD")
        res = self.request_deposit()
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"]["code"], "currency_not_supported")
        post.assert_not_called()

    def test_malformed_callback_is_rejected(self, post, get):
        res = self.send_callback({"Body": {"something": "else"}})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"]["code"], "invalid_callback")

    def test_requires_login(self, post, get):
        self.client.force_authenticate(None)
        self.assertEqual(self.request_deposit().status_code, 401)

    @override_settings(FLUXPAY_PAYMENT_PROVIDERS=FAKE)
    def test_unavailable_without_daraja_settings(self, post, get):
        res = self.request_deposit()
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"]["code"], "rail_unavailable")
