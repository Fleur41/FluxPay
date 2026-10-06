from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from audit.services import record
from fluxpay.exceptions import BusinessError

from . import mfa
from .serializers import (
    FluxPayTokenSerializer,
    MfaCodeSerializer,
    MfaDisableSerializer,
    MfaLoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
    tokens_for,
)

User = get_user_model()


class LoginView(TokenObtainPairView):
    serializer_class = FluxPayTokenSerializer


class RegisterView(generics.CreateAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = serializer.save()
            record("auth.registered", actor=user)
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MfaLoginView(APIView):
    """POST auth/login/mfa/ {mfa_token, code}: the second step of signing in. The code may be a recovery code."""

    authentication_classes = ()
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "mfa"

    def post(self, request):
        serializer = MfaLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = mfa.user_from_challenge(serializer.validated_data["mfa_token"])
        mfa.check(user, serializer.validated_data["code"])
        return Response(tokens_for(user))


class MfaView(APIView):
    """GET auth/mfa/: whether two-step verification is on, and whether this account needs it."""

    def get(self, request):
        user = request.user
        left = user.mfa_recovery_codes.filter(used_at__isnull=True).count() if user.mfa_enabled else 0
        return Response({"enabled": user.mfa_enabled, "required": mfa.is_required(user), "recovery_codes_left": left})


class MfaSetupView(APIView):
    """POST auth/mfa/setup/: a new secret to add to an authenticator app (as `otpauth_uri` or typed in)."""

    def post(self, request):
        if request.user.mfa_enabled:
            raise BusinessError("Two-step verification is already on.", "mfa_already_enabled")
        secret, uri = mfa.begin_setup(request.user)
        return Response({"secret": secret, "otpauth_uri": uri})


class MfaEnableView(APIView):
    """POST auth/mfa/enable/ {code}: confirms the app works; answers with the recovery codes (shown once)."""

    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "mfa"

    def post(self, request):
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"recovery_codes": mfa.enable(request.user, serializer.validated_data["code"])})


class MfaDisableView(APIView):
    """POST auth/mfa/disable/ {password, code}."""

    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "mfa"

    def post(self, request):
        serializer = MfaDisableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mfa.disable(request.user, serializer.validated_data["password"], serializer.validated_data["code"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MfaRecoveryCodesView(APIView):
    """POST auth/mfa/recovery-codes/ {code}: new recovery codes; the old ones stop working."""

    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "mfa"

    def post(self, request):
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"recovery_codes": mfa.new_recovery_codes(request.user, serializer.validated_data["code"])})


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class LogoutView(APIView):
    """Blacklists the refresh token so it can't be used again."""

    def post(self, request):
        record("auth.logout", actor=request.user)
        token = request.data.get("refresh")
        if token:
            try:
                RefreshToken(token).blacklist()
            except Exception:  # already invalid/expired: logging out is still a success
                pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"], is_active=True).first()
        if user:
            link = settings.PASSWORD_RESET_LINK.format(
                uid=urlsafe_base64_encode(force_bytes(user.pk)),
                token=default_token_generator.make_token(user),
            )
            send_mail(
                subject="Reset your FluxPay password",
                message=f"Hi {user.full_name},\n\nOpen this link to choose a new password (it works once):\n{link}\n\n"
                "If you didn't ask for this, you can ignore this email.",
                from_email=None,
                recipient_list=[user.email],
            )
        # Same response whether or not the email exists, to avoid account enumeration.
        return Response({"detail": "If that email is registered, a reset link is on its way."})


class PasswordResetConfirmView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        with transaction.atomic():
            user.set_password(serializer.validated_data["new_password"])
            user.save(update_fields=["password"])
            record("auth.password_reset", actor=user)
        return Response({"detail": "Password updated. You can now sign in."})
