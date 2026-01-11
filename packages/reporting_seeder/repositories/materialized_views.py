"""Repository for creating/updating materialized views from manifest queries."""
from __future__ import annotations

from typing import Dict, Optional

from packages.etl_core.database.client import DatabaseClient


class MaterializedViewRepository:
    def __init__(self, db_client: DatabaseClient) -> None:
        self._db = db_client

    def create_or_replace_view(self, table_name: str, query: str) -> None:
        sql = f"""
        DROP MATERIALIZED VIEW IF EXISTS {table_name};
        CREATE MATERIALIZED VIEW {table_name} AS
        {query};
        """
        self._db.execute_query(sql)

    def refresh_view(self, table_name: str) -> None:
        sql = f"REFRESH MATERIALIZED VIEW CONCURRENTLY {table_name};"
        self._db.execute_query(sql)

    def analyze_view(self, table_name: str) -> None:
        sql = f"ANALYZE {table_name};"
        self._db.execute_query(sql)

    def view_exists(self, table_name: str) -> bool:
        sql = """
        SELECT EXISTS (
            SELECT 1
            FROM pg_matviews
            WHERE schemaname || '.' || matviewname = %s
        ) AS exists
        """
        rows = self._db.execute_query(sql, [table_name])
        if not rows:
            return False
        row: Dict[str, object] = rows[0]
        return bool(row.get("exists"))

    def get_view_stats(self, table_name: str) -> Dict[str, int]:
        """Return row count and total relation size (bytes) for the view."""
        # Note: count(*) can be slow on large tables; consider pg_class.reltuples if approximation is okay.
        # Ideally reporting views are optimized for read but exact count is safer for "Records Processed".
        sql = f"""
        SELECT
            (SELECT count(*) FROM {table_name}) AS row_count,
            pg_total_relation_size(%s) AS total_bytes
        """
        try:
            rows = self._db.execute_query(sql, [table_name])
            if rows:
                return {
                    "row_count": int(rows[0].get("row_count", 0)),
                    "total_bytes": int(rows[0].get("total_bytes", 0)),
                }
        except Exception:
            # Fallback if view doesn't exist or permissions fail
            pass
        return {"row_count": 0, "total_bytes": 0}
