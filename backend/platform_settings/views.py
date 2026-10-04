from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import AppConfigSerializer
from .services import enabled_currencies, platform


class AppConfigView(APIView):
    """GET /config/ — business rules for the app. Public: the sign-up screen needs the currency list."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        rules = platform()
        data = {
            "currencies": enabled_currencies(),
            "default_currency": rules.default_currency_id,
            "statement_max_days": rules.statement_max_days,
            "session_timeout_minutes": rules.session_timeout_minutes,
            "budget_guideline": {
                "needs": rules.budget_needs_percent,
                "wants": rules.budget_wants_percent,
                "savings": rules.budget_savings_percent,
            },
        }
        return Response(AppConfigSerializer(data).data)
