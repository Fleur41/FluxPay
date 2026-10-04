from rest_framework import generics

from .serializers import NotificationSettingsSerializer
from .services import settings_for


class NotificationSettingsView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /notifications/settings/ — which channels transaction alerts go to."""

    serializer_class = NotificationSettingsSerializer
    http_method_names = ("get", "patch", "head", "options")

    def get_object(self):
        return settings_for(self.request.user)
