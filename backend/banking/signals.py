from django.dispatch import Signal

# Sent inside the transaction that moved the money; receivers that do outside work must use on_commit.
# kwargs: transfer (banking.models.Transfer)
transfer_completed = Signal()

# Sent inside the transaction that posted a staff top-up or correction (same on_commit rule).
# kwargs: adjustment (banking.models.ManualAdjustment)
adjustment_posted = Signal()
