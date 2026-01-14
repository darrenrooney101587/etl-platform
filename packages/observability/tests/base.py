"""Test helpers for observability."""
from __future__ import annotations

import unittest

from django.core.management import call_command

from observability.bootstrap import bootstrap

# Configure Django before importing models
bootstrap()
from observability.models import JobOwnerOverride, Signal, SignalGroup, SignalGroupActivity, TenantOwner, UserSlackMap  # noqa: E402


class ObservabilityTestCase(unittest.TestCase):
    """Base test case that bootstraps Django and clears state."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        bootstrap()
        call_command("migrate", run_syncdb=True, verbosity=0)

    def setUp(self) -> None:
        SignalGroupActivity.objects.all().delete()
        SignalGroup.objects.all().delete()
        Signal.objects.all().delete()
        TenantOwner.objects.all().delete()
        JobOwnerOverride.objects.all().delete()
        UserSlackMap.objects.all().delete()
