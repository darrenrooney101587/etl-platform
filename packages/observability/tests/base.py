"""Test helpers for observability."""
from __future__ import annotations

import unittest

from django.core.management import call_command
from django.db import connection

from observability.bootstrap import bootstrap

# Configure Django before importing models
bootstrap()
from observability.models import (  # noqa: E402
    NotificationJobOwnerOverride,
    NotificationSignal,
    NotificationSignalGroup,
    NotificationSignalGroupActivity,
    NotificationAgencyOwner,
    NotificationUserSlackMap,
)


class ObservabilityTestCase(unittest.TestCase):
    """Base test case that bootstraps Django and clears state."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        bootstrap()
        call_command("migrate", run_syncdb=True, verbosity=0)
        cls._ensure_tables()

    @staticmethod
    def _ensure_tables() -> None:
        existing = set(connection.introspection.table_names())
        needed_models = [
            NotificationSignal,
            NotificationSignalGroup,
            NotificationSignalGroupActivity,
            NotificationAgencyOwner,
            NotificationJobOwnerOverride,
            NotificationUserSlackMap,
        ]
        with connection.schema_editor() as editor:
            for model in needed_models:
                if model._meta.db_table not in existing:
                    editor.create_model(model)

    def setUp(self) -> None:
        NotificationSignalGroupActivity.objects.all().delete()
        NotificationSignalGroup.objects.all().delete()
        NotificationSignal.objects.all().delete()
        NotificationAgencyOwner.objects.all().delete()
        NotificationJobOwnerOverride.objects.all().delete()
        NotificationUserSlackMap.objects.all().delete()
