"""A provider with no outside service, for tests and local development. Never enabled when DEBUG is off.

Its behaviour comes from the payment's metadata:
    fake_reject   -> start_deposit / start_payout raise ProviderError
    fake_outcome  -> what fetch_status reports: succeeded (default), failed, pending or unknown
    fake_amount   -> the amount fetch_status reports, to exercise the mismatch check
"""
from decimal import Decimal

from .base import (
    Callback,
    InvalidCallback,
    PaymentProvider,
    ProviderError,
    ProviderState,
    StatusResult,
    SubmitResult,
)


class FakeProvider(PaymentProvider):
    def start_deposit(self, payment) -> SubmitResult:
        return self._submit(payment)

    def start_payout(self, payment) -> SubmitResult:
        return self._submit(payment)

    def fetch_status(self, payment) -> StatusResult:
        state = ProviderState(payment.metadata.get("fake_outcome", ProviderState.SUCCEEDED))
        amount = Decimal(payment.metadata.get("fake_amount", payment.amount))
        return StatusResult(
            state=state,
            amount=amount,
            currency=payment.currency,
            provider_ref=self._ref(payment),
            reason="Declined by the fake provider" if state == ProviderState.FAILED else "",
        )

    def parse_callback(self, headers: dict, payload: dict) -> Callback:
        event_id, provider_ref = payload.get("event_id"), payload.get("provider_ref")
        if not isinstance(event_id, str) or not isinstance(provider_ref, str) or not event_id or not provider_ref:
            raise InvalidCallback("A fake callback needs event_id and provider_ref.")
        return Callback(event_id=event_id, provider_ref=provider_ref)

    def _submit(self, payment) -> SubmitResult:
        if payment.metadata.get("fake_reject"):
            raise ProviderError("Rejected by the fake provider")
        return SubmitResult(provider_ref=self._ref(payment))

    @staticmethod
    def _ref(payment) -> str:
        return f"FAKE-{payment.reference}"
