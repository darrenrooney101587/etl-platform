"""Repository for creating/updating materialized views from manifest queries."""
from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

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
        self._db.execute_query(sql)

    def refresh_view(self, table_name: str, concurrently: bool = True) -> None:
        """Refresh the materialized view.

        Args:
            table_name: Fully qualified table name (schema.name).
            concurrently: If True, attempt CONCURRENTLY refresh first.
        """
        if concurrently:
            sql = f"REFRESH MATERIALIZED VIEW CONCURRENTLY {table_name};"
            try:
                self._db.execute_query(sql)
                return
            except Exception as exc:
                msg = str(exc)
                # Detect common Postgres error message for concurrent refresh prerequisites
                if "cannot refresh materialized view" in msg and "concurrently" in msg:
                    logger.warning("Concurrent refresh failed for %s, falling back to non-concurrent: %s", table_name, msg)
                else:
                    # Re-raise unexpected exceptions
                    raise

        # Non-concurrent refresh
        sql = f"REFRESH MATERIALIZED VIEW {table_name};"
        self._db.execute_query(sql)

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

    def get_view_definition(self, table_name: str) -> Optional[str]:
        """Return the SQL definition of the materialized view, or None if not found."""
        sql = """
        SELECT definition
        FROM pg_matviews
        WHERE schemaname || '.' || matviewname = %s
        """
        rows = self._db.execute_query(sql, [table_name])
        if rows:
            return str(rows[0].get("definition", ""))
        return None

    def get_view_columns(self, table_name: str) -> List[str]:
        """Return list of column names for the materialized view."""
        parts = table_name.split(".")
        if len(parts) == 2:
            schema, name = parts
        else:
            schema, name = "public", table_name
        sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """
        rows = self._db.execute_query(sql, [schema, name])
        return [str(r.get("column_name", "")) for r in rows]

    def query_changed(self, table_name: str, new_query: str) -> bool:
        """Check if the manifest query differs from the current view definition.

        We compare hashes of column counts as a quick heuristic. If the number of
        columns changed, the query definitely changed. For more precise detection,
        we could compare normalized SQL, but column count is a fast proxy.
        """
        if not self.view_exists(table_name):
            return True  # No existing view; must create

        current_cols = self.get_view_columns(table_name)
        # Create a temp view to count columns from the new query would be expensive;
        # instead, compare stored definition hash vs new query hash
        current_def = self.get_view_definition(table_name)
        if not current_def:
            return True

        # Normalize and hash both queries
        def normalize(q: str) -> str:
            return " ".join(q.lower().split())

        current_hash = hashlib.md5(normalize(current_def).encode()).hexdigest()
        new_hash = hashlib.md5(normalize(new_query).encode()).hexdigest()

        if current_hash != new_hash:
            logger.info("Query changed for %s (hash mismatch)", table_name)
            return True

        return False

    def has_unique_index(self, table_name: str) -> bool:
        """Check if the materialized view has a unique index (required for CONCURRENTLY)."""
        parts = table_name.split(".")
        if len(parts) == 2:
            schema, name = parts
        else:
            schema, name = "public", table_name
        sql = """
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = %s
              AND tablename = %s
              AND indexdef ILIKE '%%unique%%'
        ) AS has_unique
        """
        rows = self._db.execute_query(sql, [schema, name])
        if rows:
            return bool(rows[0].get("has_unique"))
        return False

    # Note: auto-creating unique indexes is intentionally removed. Creating
    # indexes requires domain knowledge to pick safe unique keys and should be
    # performed manually by DB owners or via a controlled migration process.

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

    def get_pg_stat_statements_for_query(self, query_pattern: str) -> Optional[Dict[str, object]]:
        """Fetch pg_stat_statements metrics for a query matching the pattern.

        Requires pg_stat_statements extension to be enabled. Returns None if not available.
        """
        sql = """
        SELECT
            calls,
            total_exec_time AS total_time_ms,
            mean_exec_time AS mean_time_ms,
            rows,
            shared_blks_hit,
            shared_blks_read,
            temp_blks_read,
            temp_blks_written
        FROM pg_stat_statements
        WHERE query ILIKE %s
        ORDER BY total_exec_time DESC
        LIMIT 1
        """
        try:
            rows = self._db.execute_query(sql, [f"%{query_pattern}%"])
            if rows:
                return dict(rows[0])
        except Exception as exc:
            # pg_stat_statements may not be enabled
            logger.debug("pg_stat_statements not available: %s", exc)
        return None

    def get_pg_stat_activity_for_view(self, table_name: str) -> Optional[Dict[str, object]]:
        """Get current activity stats for queries touching this view.

        This can help identify long-running queries.
        """
        sql = """
        SELECT
            pid,
            state,
            query_start,
            now() - query_start AS duration,
            wait_event_type,
            wait_event,
            query
        FROM pg_stat_activity
        WHERE query ILIKE %s
          AND state != 'idle'
        ORDER BY query_start
        LIMIT 1
        """
        try:
            rows = self._db.execute_query(sql, [f"%{table_name}%"])
            if rows:
                return dict(rows[0])
        except Exception:
            pass
        return None

    def get_active_db_query_count(self) -> int:
        """Return count of currently active (non-idle) queries in the database.

        This uses pg_stat_activity and filters out idle connections. It returns 0
        if pg_stat_activity is unavailable or permission is denied.
        """
        sql = """
        SELECT count(*) AS active
        FROM pg_stat_activity
        WHERE state != 'idle'
        """
        try:
            rows = self._db.execute_query(sql)
            if rows:
                return int(rows[0].get("active", 0))
        except Exception as exc:
            logger.debug("pg_stat_activity not available for active query count: %s", exc)
        return 0
