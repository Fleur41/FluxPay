"""Bank payouts sent by FluxPay staff from FluxPay's own bank account. There is no bank API.

start_payout puts the payout in the staff queue (admin: External payments, "Waiting for staff"). Staff pay
it from the bank's online banking, then confirm it with the bank's reference
(payments.services.confirm_bank_payout), which also records the payment in FluxPay's cashbook; or reject
it (payments.services.staff_fail_payout), which returns the money. fetch_status reports what staff recorded.
Money only comes in by bank through the cashbook: staff credit a wallet from a recorded bank receipt.
"""

from .base import (
    Callback,
    InvalidCallback,
    PaymentProvider,
    ProviderError,
    ProviderState,
    StatusResult,
    SubmitResult,
)


class ManualBankProvider(PaymentProvider):
    def start_deposit(self, payment) -> SubmitResult:
        raise ProviderError("Bank deposits are paid into FluxPay's bank account and credited by staff.")

    def start_payout(self, payment) -> SubmitResult:
        return SubmitResult(provider_ref=payment.reference)  # now waiting for staff

    def fetch_status(self, payment) -> StatusResult:
        outcome = payment.metadata.get("staff_outcome")
        if outcome == "sent":
            return StatusResult(state=ProviderState.SUCCEEDED, provider_ref=payment.provider_ref)
        if outcome == "failed":
            return StatusResult(state=ProviderState.FAILED, reason=payment.metadata.get("staff_note", ""))
        return StatusResult(state=ProviderState.PENDING)

    def parse_callback(self, headers: dict, payload: dict) -> Callback:
        raise InvalidCallback("Bank payouts are confirmed by staff, not by callback.")
