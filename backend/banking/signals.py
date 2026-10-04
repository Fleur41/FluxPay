from django.dispatch import Signal

# Sent inside the transaction that moved the money; receivers that do outside work must use on_commit.
# kwargs: transfer (banking.models.Transfer)
transfer_completed = Signal()
