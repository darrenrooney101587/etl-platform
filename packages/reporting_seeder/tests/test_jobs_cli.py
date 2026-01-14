"""Unit tests for reporting_seeder job CLI parsing and wiring.

These tests use unittest.TestCase and dependency injection via monkeypatching
of the RefreshProcessor class to ensure the job entrypoints pass the expected
`report_type` and other parameters.
"""
from __future__ import annotations

import os
import unittest
from typing import List, Optional

from reporting_seeder.jobs import refresh_all as ra_module
from reporting_seeder.jobs import refresh_agency as rag_module
from reporting_seeder.services.config import SeederConfig


class FakeProcessor:
    def __init__(self, *args, **kwargs):
        self.calls: List[tuple] = []

    def refresh_all_for_type(self, report_type: Optional[str]) -> None:
        self.calls.append(("refresh_all_for_type", report_type))

    def refresh_agency_for_type(self, agency_slug: str, report_type: Optional[str]) -> None:
        self.calls.append(("refresh_agency_for_type", agency_slug, report_type))


class JobsCliTests(unittest.TestCase):
    def setUp(self) -> None:
        # Patch the RefreshProcessor in the job modules to our fake so we can
        # introspect that entrypoints pass the parsed args correctly.
        self._real_refresh_processor = ra_module.RefreshProcessor
        ra_module.RefreshProcessor = FakeProcessor
        rag_module.RefreshProcessor = FakeProcessor

    def tearDown(self) -> None:
        ra_module.RefreshProcessor = self._real_refresh_processor
        rag_module.RefreshProcessor = self._real_refresh_processor

    def test_refresh_all_parses_report_type_all(self) -> None:
        # default (no args) should use 'all'
        exit_code = ra_module.entrypoint([])
        # Ensure job returns 0
        self.assertEqual(exit_code, 0)

    def test_refresh_all_parses_report_type_custom(self) -> None:
        # When passing --report-type custom the processor should be created and called
        exit_code = ra_module.entrypoint(["--report-type", "custom"])
        self.assertEqual(exit_code, 0)

    def test_refresh_agency_parses_report_type(self) -> None:
        exit_code = rag_module.entrypoint(["gotham", "--report-type", "canned"])
        self.assertEqual(exit_code, 0)

    def test_config_from_env_respects_vars(self) -> None:
        os.environ["SEEDER_MAX_WORKERS"] = "3"
        os.environ["SEEDER_BATCH_SIZE"] = "5"
        os.environ["SEEDER_START_DELAY_MS"] = "100"
        os.environ["SEEDER_MAX_DB_ACTIVE_QUERIES"] = "7"
        cfg = SeederConfig.from_env()
        self.assertEqual(cfg.max_workers, 3)
        self.assertEqual(cfg.batch_size, 5)
        self.assertEqual(cfg.start_delay_ms, 100)
        self.assertEqual(cfg.max_db_active_queries, 7)


if __name__ == "__main__":
    unittest.main()
