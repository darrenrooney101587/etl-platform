import unittest
from typing import Any, Dict, List, Optional

from reporting_seeder.repositories.history import HistoryRepository


class _FakeDBClient:
    def __init__(self) -> None:
        self.rows: List[Any] = []
        self.calls: List[Dict[str, Any]] = []

    def execute_query(self, sql: str, params: Optional[List[Any]] = None):
        self.calls.append({"sql": sql, "params": params})
        # emulate returning rows for list_recent_runs
        if sql.strip().upper().startswith("SELECT"):
            return [{"run_id": "r1"}]
        return []


class HistoryRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = _FakeDBClient()
        self.repo = HistoryRepository(self.db)

    def test_record_start_inserts(self) -> None:
        manifest = {"id": 123, "table_name": "reporting.stg_a", "report_name": "A", "agency_id": 5, "agency_slug": "g"}
        self.repo.record_start("run-1", manifest)
        self.assertTrue(any("INSERT INTO reporting.seeder_run_history" in c["sql"] for c in self.db.calls))
        self.assertTrue(any("INSERT INTO reporting.seeder_job_status" in c["sql"] for c in self.db.calls))

    def test_record_success_updates(self) -> None:
        manifest = {"id": 123, "table_name": "t"}
        self.repo.record_success("run-1", manifest, 10, 100, 1000, 50, 20)
        self.assertTrue(any("UPDATE reporting.seeder_run_history" in c["sql"] for c in self.db.calls))
        self.assertTrue(any("UPDATE reporting.seeder_job_status" in c["sql"] for c in self.db.calls))

    def test_record_error_updates(self) -> None:
        manifest = {"id": 123, "table_name": "t"}
        self.repo.record_error("run-1", manifest, "boom")
        self.assertTrue(any("UPDATE reporting.seeder_run_history" in c["sql"] for c in self.db.calls))
        self.assertTrue(any("UPDATE reporting.seeder_job_status" in c["sql"] for c in self.db.calls))

    def test_list_recent_runs_returns_rows(self) -> None:
        rows = self.repo.list_recent_runs(limit=5)
        self.assertEqual(rows, [{"run_id": "r1"}])


if __name__ == "__main__":
    unittest.main()
