from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from audit.services import record
from fluxpay.exceptions import BusinessError
from platform_settings import services as rules

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "full_name", "phone_number", "date_joined")
        read_only_fields = ("id", "email", "date_joined")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    # Any currency staff have enabled (platform_settings); the platform default when left out.
    currency = serializers.CharField(max_length=3, write_only=True, required=False)

    class Meta:
        model = User
        fields = ("email", "full_name", "phone_number", "password", "currency")

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_currency(self, value):
        try:
            return rules.currency(value).code
        except BusinessError as exc:
            raise serializers.ValidationError(str(exc.detail)) from None

    def validate(self, attrs):
        candidate = User(email=attrs["email"], full_name=attrs.get("full_name", ""))
        password_validation.validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        from banking.services import open_wallet

        currency = validated_data.pop("currency", None)
        user = User.objects.create_user(**validated_data)
        open_wallet(user, currency=currency)
        return user


class FluxPayTokenSerializer(TokenObtainPairSerializer):
    """Login response also carries the user profile to save a round-trip."""

    def validate(self, attrs):
        attrs[self.username_field] = attrs[self.username_field].lower()
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        record("auth.login", actor=self.user)
        return data


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(attrs["uid"])))
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            raise serializers.ValidationError("This reset link is invalid.")
        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError("This reset link is invalid or has expired.")
        password_validation.validate_password(attrs["new_password"], user=user)
        attrs["user"] = user
        return attrs
