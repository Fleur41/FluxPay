from django.urls import path

from .views import AppConfigView

urlpatterns = [path("config/", AppConfigView.as_view(), name="app-config")]
