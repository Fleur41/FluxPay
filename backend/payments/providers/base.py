"""The interface every payment rail implements. The ledger never talks to a provider directly."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class ProviderState(StrEnum):
    PENDING = "pending"  # the provider has it but there is no outcome yet
    SUCCEEDED = "succeeded"
    FAILED = "failed"  # a definite failure: no money moved at the provider
    UNKNOWN = "unknown"  # no clear answer (timeout, outage); never treated as a failure


@dataclass(frozen=True)
class SubmitResult:
    provider_ref: str
    metadata: dict = field(default_factory=dict)  # safe extras to keep on the payment, e.g. an approval URL


@dataclass(frozen=True)
class StatusResult:
    state: ProviderState
    amount: Decimal | None = None
    currency: str | None = None
    provider_ref: str = ""
    reason: str = ""


@dataclass(frozen=True)
class Callback:
    event_id: str  # the provider's id for this notification; used to drop replays
    provider_ref: str  # finds the payment the notification is about
    details: dict = field(default_factory=dict)  # safe extras kept on the payment, e.g. "provider_receipt"


class ProviderError(Exception):
    """The provider rejected the request outright (invalid number, failed validation). No money moved."""


class ProviderUnavailable(Exception):
    """The provider could not be reached or gave no clear answer. Retry later; never fail a payment on this."""


class InvalidCallback(Exception):
    """A callback that is malformed or fails the provider's authenticity check."""


class PaymentProvider(ABC):
    #: Currencies this provider settles in; None means any wallet currency.
    currencies: frozenset[str] | None = None
    #: True when amounts must be whole units (M-Pesa takes whole shillings).
    whole_units_only: bool = False
    #: False when submitting the same payout twice could pay twice. payments.services then never resubmits
    #: a payout whose first attempt went unanswered; it is flagged for staff instead.
    payouts_idempotent: bool = True

    @classmethod
    def can_pay_out(cls) -> bool:
        """False when this server isn't set up to send payouts on the rail (e.g. missing credentials)."""
        return True

    @abstractmethod
    def start_deposit(self, payment) -> SubmitResult:
        """Ask the provider to collect `payment.amount` into FluxPay (e.g. send the customer a payment prompt)."""

    @abstractmethod
    def start_payout(self, payment) -> SubmitResult:
        """Send `payment.amount` out of FluxPay.

        Must be idempotent on `payment.reference` (pass it as the provider's idempotency key or
        originator id): a payout whose first attempt timed out is submitted again, and must not pay twice.
        """

    @abstractmethod
    def fetch_status(self, payment) -> StatusResult:
        """Ask the provider what happened to `payment`.

        Must find the payment by `payment.reference` when `provider_ref` is still blank, because a
        submit that timed out may have reached the provider without us learning its reference.
        """

    @abstractmethod
    def parse_callback(self, headers: dict, payload: dict) -> Callback:
        """Check a callback is authentic and well formed, or raise InvalidCallback.

        The callback's claimed outcome is never applied directly: the payment is settled from
        `fetch_status`, so a forged or stale callback can at most trigger a status check.
        """
