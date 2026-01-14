"""AppConfig for the observability notification service."""
from __future__ import annotations

from django.apps import AppConfig


class ObservabilityConfig(AppConfig):
    """Django application configuration for observability."""

    name = "observability"
    verbose_name = "Observability"
    default_auto_field = "django.db.models.BigAutoField"
