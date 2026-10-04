from django.dispatch import Signal

# Sent inside the transaction that settled the payment; receivers that do outside work must use on_commit.
# kwargs: payment (payments.models.ExternalPayment), in a final state: COMPLETED, FAILED or REVERSED
payment_settled = Signal()
