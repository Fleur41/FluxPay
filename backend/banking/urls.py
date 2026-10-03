from django.urls import path

from .views import (
    AccountListView,
    AccountLookupView,
    TransactionDetailView,
    TransactionListView,
    TransferCreateView,
)

urlpatterns = [
    path("accounts/", AccountListView.as_view(), name="account-list"),
    path("accounts/lookup/", AccountLookupView.as_view(), name="account-lookup"),
    path("transactions/", TransactionListView.as_view(), name="transaction-list"),
    path("transactions/<uuid:pk>/", TransactionDetailView.as_view(), name="transaction-detail"),
    path("transfers/", TransferCreateView.as_view(), name="transfer-create"),
]
