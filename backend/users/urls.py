from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginView,
    LogoutView,
    MeView,
    MfaDisableView,
    MfaEnableView,
    MfaLoginView,
    MfaRecoveryCodesView,
    MfaSetupView,
    MfaView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("login/mfa/", MfaLoginView.as_view(), name="login-mfa"),
    path("mfa/", MfaView.as_view(), name="mfa"),
    path("mfa/setup/", MfaSetupView.as_view(), name="mfa-setup"),
    path("mfa/enable/", MfaEnableView.as_view(), name="mfa-enable"),
    path("mfa/disable/", MfaDisableView.as_view(), name="mfa-disable"),
    path("mfa/recovery-codes/", MfaRecoveryCodesView.as_view(), name="mfa-recovery-codes"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
]
