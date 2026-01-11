import unittest
from typing import Any, Dict, List, Optional

from reporting_seeder.repositories.materialized_views import MaterializedViewRepository


class _FakeDBClient:
    def __init__(self) -> None:
        self.queries: List[str] = []

    def execute_query(self, sql: str, params: Optional[List[Any]] = None):
        # record canonicalized SQL for assertions
        self.queries.append(sql.strip())
        return []


class MaterializedViewsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = _FakeDBClient()
        self.repo = MaterializedViewRepository(self.db)

    def test_create_or_replace_view_emits_sql(self) -> None:
        self.repo.create_or_replace_view("reporting.mv_test", "select 1 as c")
        self.assertTrue(any("CREATE MATERIALIZED VIEW reporting.mv_test AS" in q for q in self.db.queries))

    def test_refresh_view_emits_refresh_sql(self) -> None:
        self.repo.refresh_view("reporting.mv_test")
        self.assertTrue(any("REFRESH MATERIALIZED VIEW CONCURRENTLY reporting.mv_test" in q for q in self.db.queries))

    def test_analyze_view_emits_analyze_sql(self) -> None:
        self.repo.analyze_view("reporting.mv_test")
        self.assertTrue(any(q.startswith("ANALYZE reporting.mv_test") for q in self.db.queries))

    def test_view_exists_calls_pg_matviews(self) -> None:
        self.repo.view_exists("reporting.mv_test")
        self.assertTrue(any("pg_matviews" in q for q in self.db.queries))


if __name__ == "__main__":
    unittest.main()
