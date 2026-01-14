import os
import time
import unittest
import uuid
from typing import Any, Dict, List

# Attempt to load a local .env file (packages/reporting_seeder/.env) for integration tests.
# This keeps tests runnable locally without requiring manual env export when developers
# keep a .env in the package directory.
try:
    from pathlib import Path
    from dotenv import load_dotenv  # type: ignore

    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except Exception:
    # dotenv isn't required; tests will still work if environment vars are exported.
    pass

from etl_core.support.circuit_breaker import CircuitBreaker
from etl_core.support.executor import ParallelExecutor
from etl_core.database.client import DatabaseClient
from reporting_seeder.repositories.manifests import ManifestRepository
from reporting_seeder.repositories.materialized_views import MaterializedViewRepository
from reporting_seeder.repositories.history import HistoryRepository
from reporting_seeder.services.config import SeederConfig
from reporting_seeder.processors.refresh import RefreshProcessor


INTEGRATION_ENV = "RUN_SEEDER_INTEGRATION"


@unittest.skipUnless(os.getenv(INTEGRATION_ENV) == "1", "Integration test disabled; set RUN_SEEDER_INTEGRATION=1 to enable")
class SeederLoadIntegrationTest(unittest.TestCase):
    """Integration test that creates 5 simple manifests and runs them in parallel.

    This test talks to the real Postgres database configured via env vars.
    It inserts 5 temporary manifest rows that each create a materialized view
    selecting a generate_series to simulate workload. After running the
    seeder, it verifies history rows were recorded with status 'success'.

    The test is skipped by default; set RUN_SEEDER_INTEGRATION=1 before running.
    """

    def setUp(self) -> None:
        self.db = DatabaseClient()
        self.config = SeederConfig.from_env()
        self.manifest_repo = ManifestRepository(self.db)
        self.mv_repo = MaterializedViewRepository(self.db)
        self.history_repo = HistoryRepository(self.db)
        self.cb = CircuitBreaker(max_failures=5, reset_seconds=60)
        self.executor = ParallelExecutor(max_workers=5)
        self.processor = RefreshProcessor(
            manifest_repository=self.manifest_repo,
            history_repository=self.history_repo,
            mv_repository=self.mv_repo,
            executor=self.executor,
            circuit_breaker=self.cb,
            config=self.config,
        )

        # Prepare 5 manifests in reporting.seeder_custom_report_manifest. Use unique table names.
        self.test_tables: List[str] = []
        self.inserted_manifest_ids: List[int] = []
        for i in range(5):
            uid = uuid.uuid4().hex[:8]
            table_name = f"reporting.test_seeder_mv_{uid}_{i}"
            self.test_tables.append(table_name)

            query = f"SELECT generate_series(1, 20000) AS n"  # moderate-sized result
            # Insert manifest row; explicitly specify columns to match schema
            sql = (
                "INSERT INTO reporting.seeder_custom_report_manifest "
                "(table_name, report_name, agency_id, agency_slug, query, database_id, enabled) "
                "VALUES (%s, %s, %s, %s, %s, %s, TRUE) RETURNING id"
            )
            rows = self.db.execute_query(sql, [table_name, f"load_test_{i}", 1, "test", query, 1])
            # DatabaseClient returns rows for SELECT/RETURNING; pick inserted id if present else track 0
            if rows:
                self.inserted_manifest_ids.append(int(rows[0].get("id", 0)))
            else:
                self.inserted_manifest_ids.append(0)

    def tearDown(self) -> None:
        # Drop materialized views and delete manifests and history entries
        for table in self.test_tables:
            try:
                self.db.execute_query(f"DROP MATERIALIZED VIEW IF EXISTS {table};")
            except Exception:
                pass
        # Delete manifests we inserted
        try:
            self.db.execute_query("DELETE FROM reporting.seeder_custom_report_manifest WHERE table_name LIKE 'reporting.test_seeder_mv_%';")
            self.db.execute_query("DELETE FROM reporting.seeder_run_history WHERE table_name LIKE 'reporting.test_seeder_mv_%';")
            self.db.execute_query("DELETE FROM reporting.seeder_job_status WHERE table_name LIKE 'reporting.test_seeder_mv_%';")
        except Exception:
            pass

    def test_load_5_parallel(self) -> None:
        # Ensure manifests are visible and enabled then run a refresh_all
        manifests = self.manifest_repo.get_enabled_manifests()
        # Filter to our test tables
        manifests = [m for m in manifests if m.get("table_name") in self.test_tables]
        self.assertEqual(len(manifests), 5, "Expected 5 test manifests to be present")

        start = time.time()
        # Kick off processing (processor.refresh_all will run them in parallel according to config)
        self.processor.refresh_all()
        duration = time.time() - start
        print(f"Refresh completed in {duration:.2f}s")

        # Allow a small delay for DB writes to finish
        time.sleep(0.5)

        # Verify history records for each table show success
        failures = []
        for t in self.test_tables:
            rows = self.db.execute_query(
                "SELECT status FROM reporting.seeder_run_history WHERE table_name = %s ORDER BY start_time DESC LIMIT 1",
                [t],
            )
            if not rows:
                failures.append((t, "no history"))
            else:
                status = rows[0].get("status")
                if status != "success":
                    failures.append((t, status))

        self.assertFalse(failures, f"Some manifests failed or had no history: {failures}")


if __name__ == "__main__":
    print("This is an integration test. Set RUN_SEEDER_INTEGRATION=1 to run it against a local DB.")
    unittest.main()
