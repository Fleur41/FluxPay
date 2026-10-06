from django.urls import path

from .views import (
    MpesaDepositView,
    MpesaWithdrawalView,
    PaymentDetailView,
    PaymentListView,
)

urlpatterns = [
    path("payments/", PaymentListView.as_view(), name="payment-list"),
    path("payments/<uuid:pk>/", PaymentDetailView.as_view(), name="payment-detail"),
    path("deposits/mpesa/", MpesaDepositView.as_view(), name="deposit-mpesa"),
    path("withdrawals/mpesa/", MpesaWithdrawalView.as_view(), name="withdrawal-mpesa"),
]
