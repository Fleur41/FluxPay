from rest_framework import serializers

from .models import Currency


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ("code", "name", "min_transfer", "max_transfer")


class AppConfigSerializer(serializers.Serializer):
    """What the app needs to render forms and enforce limits without hard-coding them."""

    currencies = CurrencySerializer(many=True)
    default_currency = serializers.CharField()
    statement_max_days = serializers.IntegerField()
    session_timeout_minutes = serializers.IntegerField()
    budget_guideline = serializers.DictField(child=serializers.IntegerField())
