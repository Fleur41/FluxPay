"""Celery app for background payment work. Run with: celery -A fluxpay worker -B -l info"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fluxpay.settings")

app = Celery("fluxpay")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
