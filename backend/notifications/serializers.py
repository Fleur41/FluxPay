from rest_framework import serializers

from .models import NotificationSettings


class NotificationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSettings
        fields = ("email_enabled", "sms_enabled")
