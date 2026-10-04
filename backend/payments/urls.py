from django.urls import path

from .views import PaymentDetailView, PaymentListView

urlpatterns = [
    path("payments/", PaymentListView.as_view(), name="payment-list"),
    path("payments/<uuid:pk>/", PaymentDetailView.as_view(), name="payment-detail"),
]
