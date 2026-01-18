import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
import sys
import types
from datetime import datetime

from reporting_seeder.repositories.history import HistoryRepository


class HistoryRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        # Prepare a fake models module with the ORM objects we expect
        self.SeederRunHistory = MagicMock()
        self.SeederJobStatus = MagicMock()

        # Create a fake etl_core.models models module and insert into sys.modules
        self._fake_mod_name = 'etl_core.models.apps.reporting.models'
        fake_mod = types.ModuleType(self._fake_mod_name)
        fake_mod.SeederRunHistory = self.SeederRunHistory
        fake_mod.SeederJobStatus = self.SeederJobStatus
        self._previous_models_module = sys.modules.get(self._fake_mod_name)
        sys.modules[self._fake_mod_name] = fake_mod

        # Create a minimal fake django.utils.timezone with now() to avoid Django settings
        tz_mod_name = 'django.utils.timezone'
        tz_mod = types.ModuleType(tz_mod_name)
        tz_mod.now = staticmethod(lambda: datetime.utcnow())
        self._previous_tz = sys.modules.get(tz_mod_name)
        sys.modules[tz_mod_name] = tz_mod
        # also ensure parent packages exist in sys.modules
        sys.modules.setdefault('django', types.ModuleType('django'))
        sys.modules.setdefault('django.utils', types.ModuleType('django.utils'))
        sys.modules['django.utils'].timezone = tz_mod

        # Minimal django.db.models.F mock
        db_models_name = 'django.db.models'
        db_models = types.ModuleType(db_models_name)
        class _FakeF:
            def __init__(self, name):
                self.name = name

            def __add__(self, other):
                # Return a simple representation to allow expressions like F('x') + 1
                return f"F({self.name})+{other}"

            def __radd__(self, other):
                return f"{other}+F({self.name})"

        db_models.F = _FakeF
        self._previous_db_models = sys.modules.get(db_models_name)
        sys.modules[db_models_name] = db_models
        # ensure parent packages
        sys.modules.setdefault('django.db', types.ModuleType('django.db'))
        sys.modules['django.db'].models = db_models

        self.repo = HistoryRepository()

    def tearDown(self) -> None:
        # Restore previous etl_database_schema models module
        if self._previous_models_module is not None:
            sys.modules[self._fake_mod_name] = self._previous_models_module
        else:
            sys.modules.pop(self._fake_mod_name, None)

        # Restore timezone module
        if self._previous_tz is not None:
            sys.modules['django.utils.timezone'] = self._previous_tz
        else:
            sys.modules.pop('django.utils.timezone', None)
            # remove inserted parent entries if they were created here
            sys.modules.pop('django.utils', None)
            sys.modules.pop('django', None)

        # Restore db.models
        if self._previous_db_models is not None:
            sys.modules['django.db.models'] = self._previous_db_models
        else:
            sys.modules.pop('django.db.models', None)
            sys.modules.pop('django.db', None)

    def test_record_start_creates_rows(self) -> None:
        manifest = {"id": 123, "table_name": "reporting.stg_a", "report_name": "A", "agency_id": 5, "agency_slug": "g"}
        self.repo.record_start("run-1", manifest)
        # Ensure ORM create was called
        self.assertTrue(self.SeederRunHistory.objects.create.called)
        self.assertTrue(self.SeederJobStatus.objects.update_or_create.called)

    def test_record_success_updates(self) -> None:
        manifest = {"id": 123, "table_name": "t"}
        self.repo.record_success("run-1", manifest, 10, 100, 1000, 50, 20)
        self.assertTrue(self.SeederRunHistory.objects.filter.called)
        self.assertTrue(self.SeederJobStatus.objects.filter.called)

    def test_record_error_updates(self) -> None:
        manifest = {"id": 123, "table_name": "t"}
        self.repo.record_error("run-1", manifest, "boom")
        self.assertTrue(self.SeederRunHistory.objects.filter.called)
        self.assertTrue(self.SeederJobStatus.objects.filter.called)

    def test_list_recent_runs_returns_rows(self) -> None:
        # Setup the values() return value
        qs = MagicMock()
        qs.values.return_value = [{'run_id': 'r1'}]
        self.SeederRunHistory.objects.order_by.return_value = qs
        rows = self.repo.list_recent_runs(limit=5)
        self.assertEqual(rows, [{'run_id': 'r1'}])


if __name__ == "__main__":
    unittest.main()
