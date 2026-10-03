# Load the Celery app with Django so shared tasks bind to it.
from .celery import app as celery_app

__all__ = ("celery_app",)
