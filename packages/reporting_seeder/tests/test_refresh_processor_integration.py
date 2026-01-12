import unittest
from typing import Any, Dict, List

from etl_core.support.circuit_breaker import CircuitBreaker
from etl_core.support.executor import ParallelExecutor
from reporting_seeder.processors.refresh import RefreshProcessor
from reporting_seeder.repositories.manifests import ManifestRepository
from reporting_seeder.repositories.history import HistoryRepository
from reporting_seeder.repositories.materialized_views import MaterializedViewRepository
from reporting_seeder.services.config import SeederConfig


class _FakeManifestRepo(ManifestRepository):
    def __init__(self, manifests: List[Dict[str, object]]):
        self._manifests = manifests

    def get_enabled_manifests(self) -> List[Dict[str, object]]:
        return self._manifests

    def get_enabled_manifests_for_agency(self, agency_slug: str) -> List[Dict[str, object]]:
        return [m for m in self._manifests if m.get("agency_slug") == agency_slug]

    def get_manifest_by_table(self, table_name: str):
        for m in self._manifests:
            if m.get("table_name") == table_name:
                return m
        return None


class _RecordingHistory(HistoryRepository):
    def __init__(self) -> None:
        self.actions: List[str] = []

    def record_start(self, run_id: str, manifest: Dict[str, object]) -> None:
        self.actions.append(f"start:{run_id}:{manifest['id']}")

    def record_success(self, run_id: str, manifest: Dict[str, object], duration_seconds: int, records_processed: int, bytes_processed: int, memory_usage_mb: int, cpu_percentage: int) -> None:
        self.actions.append(f"success:{run_id}:{manifest['id']}")

    def record_error(self, run_id: str, manifest: Dict[str, object], errors: str) -> None:
        self.actions.append(f"error:{run_id}:{manifest['id']}")


class _FakeMV(MaterializedViewRepository):
    def __init__(self, fail_on: str | None = None) -> None:
        self.created: List[str] = []
        self.refreshed: List[str] = []
        self.analyzed: List[str] = []
        self.fail_on = fail_on

    def view_exists(self, table_name: str) -> bool:
        return table_name in self.created

    def create_or_replace_view(self, table_name: str, query: str) -> None:
        if self.fail_on == table_name:
            raise RuntimeError("boom-create")
        self.created.append(table_name)

    def refresh_view(self, table_name: str) -> None:
        if self.fail_on == table_name:
            raise RuntimeError("boom-refresh")
        self.refreshed.append(table_name)

    def analyze_view(self, table_name: str) -> None:
        self.analyzed.append(table_name)

    def get_view_stats(self, table_name: str) -> Dict[str, int]:
        return {"row_count": 500, "total_bytes": 10240}


class RefreshProcessorIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = SeederConfig.from_env()

    def test_successful_run_records_start_and_success(self) -> None:
        manifests = [{"id": 1, "table_name": "reporting.mv_ok", "query": "select 1", "agency_slug": "g"}]
        processor = RefreshProcessor(
            manifest_repository=_FakeManifestRepo(manifests),
            history_repository=_RecordingHistory(),
            mv_repository=_FakeMV(),
            executor=ParallelExecutor(max_workers=2),
            circuit_breaker=CircuitBreaker(max_failures=2, reset_seconds=1),
            config=self.config,
        )
        processor.refresh_all()
        self.assertTrue(any(a.startswith("start:") for a in processor._history.actions))
        self.assertTrue(any(a.startswith("success:") for a in processor._history.actions))

    def test_failure_records_error_and_trips_circuit(self) -> None:
        manifests = [
            {"id": 1, "table_name": "reporting.mv_fail", "query": "select 1", "agency_slug": "g"},
            {"id": 2, "table_name": "reporting.mv_ok", "query": "select 2", "agency_slug": "g"},
        ]
        history = _RecordingHistory()
        cb = CircuitBreaker(max_failures=1, reset_seconds=10)
        processor = RefreshProcessor(
            manifest_repository=_FakeManifestRepo(manifests),
            history_repository=history,
            mv_repository=_FakeMV(fail_on="reporting.mv_fail"),
            executor=ParallelExecutor(max_workers=2),
            circuit_breaker=cb,
            config=self.config,
        )
        processor.refresh_all()
        self.assertTrue(any(a.startswith("error:") for a in history.actions))


if __name__ == "__main__":
    unittest.main()
