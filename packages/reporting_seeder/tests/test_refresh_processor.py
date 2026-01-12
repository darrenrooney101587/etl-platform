import unittest
from typing import Any, Dict, List

from etl_core.support.circuit_breaker import CircuitBreaker
from etl_core.support.executor import ParallelExecutor
from reporting_seeder.processors.refresh import RefreshProcessor
from reporting_seeder.repositories.history import HistoryRepository
from reporting_seeder.repositories.manifests import ManifestRepository
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


class _FakeHistoryRepo(HistoryRepository):
    def __init__(self) -> None:
        self.starts: List[Any] = []
        self.successes: List[Any] = []
        self.errors: List[Any] = []

    def record_start(self, run_id: str, manifest: Dict[str, object]) -> None:
        self.starts.append((run_id, manifest["id"]))

    def record_success(
        self,
        run_id: str,
        manifest: Dict[str, object],
        duration_seconds: int,
        records_processed: int,
        bytes_processed: int,
        memory_usage_mb: int,
        cpu_percentage: int,
    ) -> None:
        self.successes.append(run_id)

    def record_error(self, run_id: str, manifest: Dict[str, object], errors: str) -> None:
        self.errors.append(run_id)


class _FakeMVRepo(MaterializedViewRepository):
    def __init__(self, raise_on: str | None = None) -> None:
        self.created: List[str] = []
        self.refreshed: List[str] = []
        self.analyzed: List[str] = []
        self.raise_on = raise_on

    def view_exists(self, table_name: str) -> bool:
        return table_name in self.created

    def create_or_replace_view(self, table_name: str, query: str) -> None:
        if self.raise_on == table_name:
            raise RuntimeError("boom")
        self.created.append(table_name)

    def refresh_view(self, table_name: str) -> None:
        if self.raise_on == table_name:
            raise RuntimeError("boom")
        self.refreshed.append(table_name)

    def analyze_view(self, table_name: str) -> None:
        self.analyzed.append(table_name)

    def get_view_stats(self, table_name: str) -> Dict[str, int]:
        return {"row_count": 100, "total_bytes": 1024}


class RefreshProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = SeederConfig(
            db_host="localhost",
            db_port=5432,
            db_name="postgres",
            db_user="postgres",
            db_password="",
            max_workers=4,
            max_failures=2,
            reset_seconds=1,
            refresh_concurrently=True,
        )

    def test_refresh_all_success(self) -> None:
        manifests = [
            {"id": 1, "table_name": "reporting.mv_a", "query": "select 1", "agency_slug": "a"},
            {"id": 2, "table_name": "reporting.mv_b", "query": "select 2", "agency_slug": "b"},
        ]
        processor = RefreshProcessor(
            manifest_repository=_FakeManifestRepo(manifests),
            history_repository=_FakeHistoryRepo(),
            mv_repository=_FakeMVRepo(),
            executor=ParallelExecutor(max_workers=2),
            circuit_breaker=CircuitBreaker(max_failures=3, reset_seconds=1),
            config=self.config,
        )
        processor.refresh_all()

    def test_circuit_breaker_trips(self) -> None:
        manifests = [
            {"id": 1, "table_name": "reporting.mv_fail", "query": "select 1", "agency_slug": "a"},
            {"id": 2, "table_name": "reporting.mv_other", "query": "select 2", "agency_slug": "b"},
        ]
        processor = RefreshProcessor(
            manifest_repository=_FakeManifestRepo(manifests),
            history_repository=_FakeHistoryRepo(),
            mv_repository=_FakeMVRepo(raise_on="reporting.mv_fail"),
            executor=ParallelExecutor(max_workers=2),
            circuit_breaker=CircuitBreaker(max_failures=1, reset_seconds=10),
            config=self.config,
        )
        processor.refresh_all()


if __name__ == "__main__":
    unittest.main()
