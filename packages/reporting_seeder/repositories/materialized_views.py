"""Repository for creating/updating materialized views from manifest queries."""
from __future__ import annotations

from typing import Dict

from etl_core.database.client import DatabaseClient
import logging

logger = logging.getLogger(__name__)


class MaterializedViewRepository:
    """DDL/DML operations for materialized views."""

    def __init__(self, db_client: DatabaseClient) -> None:
        self._db = db_client

    def create_or_replace_view(self, table_name: str, query: str) -> None:
        """Drop and create the materialized view based on the manifest query."""
        sql = f"""
        DROP MATERIALIZED VIEW IF EXISTS {table_name};
        CREATE MATERIALIZED VIEW {table_name} AS
        {query};
        """
        # No params to pass; execute directly
        self._db.execute_query(sql)

    def refresh_view(self, table_name: str) -> None:
        """Refresh the materialized view, preferring CONCURRENTLY when possible.

        If the concurrent refresh fails because the materialized view doesn't
        have a unique index (postgres error), fall back to non-concurrent refresh.
        """
        sql_concurrent = f"REFRESH MATERIALIZED VIEW CONCURRENTLY {table_name};"
        try:
            # Suppress error-level logging for the expected concurrent-refresh
            # prerequisite error; fallback will be attempted below.
            self._db.execute_query(sql_concurrent, suppress_errors=True)
            return
        except Exception as exc:
            msg = str(exc)
            # Detect common Postgres error message for concurrent refresh prerequisites
            if "cannot refresh materialized view" in msg and "concurrently" in msg:
                logger.warning("Concurrent refresh failed for %s, falling back: %s", table_name, msg)
                sql = f"REFRESH MATERIALIZED VIEW {table_name};"
                self._db.execute_query(sql)
                return
            # Re-raise unexpected exceptions
            raise

    def analyze_view(self, table_name: str) -> None:
        """Run ANALYZE to update planner statistics."""
        self._db.execute_query(f"ANALYZE {table_name};")

    def view_exists(self, table_name: str) -> bool:
        """Return True if the materialized view exists."""
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
