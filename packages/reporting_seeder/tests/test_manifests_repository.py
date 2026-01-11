import unittest
from typing import Any, Dict, List, Optional

from reporting_seeder.repositories.manifests import ManifestRepository


class _FakeDBClient:
    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None) -> None:
        self.rows = rows or []
        self.last_sql: Optional[str] = None
        self.last_params: Optional[List[Any]] = None

    def execute_query(self, sql: str, params: Optional[List[Any]] = None):
        self.last_sql = sql
        self.last_params = params
        return self.rows


class ManifestsRepositoryTests(unittest.TestCase):
    def test_get_enabled_manifests_returns_rows(self) -> None:
        rows = [
            {"id": 1, "table_name": "a", "query": "select 1", "agency_slug": "x"},
            {"id": 2, "table_name": "b", "query": "select 2", "agency_slug": "y"},
        ]
        db = _FakeDBClient(rows=rows)
        repo = ManifestRepository(db)

        got = repo.get_enabled_manifests()
        self.assertEqual(got, rows)
        self.assertIsNotNone(db.last_sql)
        # Ensure the SQL references custom and canned
        self.assertIn("seeder_custom_report_manifest", db.last_sql)
        self.assertIn("seeder_canned_report", db.last_sql)

    def test_get_enabled_manifests_for_agency_passes_params(self) -> None:
        rows = [{"id": 10, "table_name": "stg_a", "query": "select 1", "agency_slug": "gotham"}]
        db = _FakeDBClient(rows=rows)
        repo = ManifestRepository(db)

        got = repo.get_enabled_manifests_for_agency("gotham")
        self.assertEqual(got, rows)
        self.assertEqual(db.last_params, ["gotham", "gotham"])

    def test_get_manifest_by_table_returns_single(self) -> None:
        rows = [{"id": 7, "table_name": "reporting.stg_a", "query": "select 1"}]
        db = _FakeDBClient(rows=rows)
        repo = ManifestRepository(db)

        got = repo.get_manifest_by_table("reporting.stg_a")
        self.assertEqual(got, rows[0])
        # Negative case: use an empty DB client to simulate no rows returned
        empty_db = _FakeDBClient(rows=[])
        repo_empty = ManifestRepository(empty_db)
        self.assertIsNone(repo_empty.get_manifest_by_table("no.such.table"))


if __name__ == "__main__":
    unittest.main()
