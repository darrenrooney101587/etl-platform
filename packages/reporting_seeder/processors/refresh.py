"""Processor to refresh reporting materialized views with concurrency and circuit breaking."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Dict, List, Optional

from etl_core.support.circuit_breaker import CircuitBreaker
from etl_core.support.executor import ParallelExecutor
from reporting_seeder.repositories.history import HistoryRepository
from reporting_seeder.repositories.manifests import ManifestRepository
from reporting_seeder.repositories.materialized_views import MaterializedViewRepository
from reporting_seeder.services.config import SeederConfig

logger = logging.getLogger(__name__)


class RefreshProcessor:
    """Orchestrates concurrent refresh of manifest-driven materialized views.

    Key behaviors:
    - Detects when a manifest query has changed and recreates the view
    - Creates unique indexes to enable CONCURRENTLY refresh
    - Captures PostgreSQL-side query statistics (not Python process stats)
    - Uses fire-and-forget parallel execution so slow queries don't block others
    """

    def __init__(
        self,
        manifest_repository: ManifestRepository,
        history_repository: HistoryRepository,
        mv_repository: MaterializedViewRepository,
        executor: ParallelExecutor,
        circuit_breaker: CircuitBreaker,
        config: SeederConfig,
    ) -> None:
        self._manifests = manifest_repository
        self._history = history_repository
        self._mv = mv_repository
        self._executor = executor
        self._circuit_breaker = circuit_breaker
        self._config = config

    def refresh_all(self) -> None:
        """Refresh all enabled manifests.

        Optional filtering by report type is supported via the `report_type`
        argument in the job entrypoint; that value is passed through to the
        repository layer which returns only the requested manifests.
        """
        # Backwards-compatible single-arg API retained (no report_type -> all)
        self.refresh_all_for_type(None)

    def refresh_all_for_type(self, report_type: Optional[str]) -> None:
        """Refresh enabled manifests optionally filtered by report_type.

        report_type: one of None|'all'|'custom'|'canned'
        """
        manifests = self._manifests.get_enabled_manifests_for_type(report_type)
        self._refresh_many(manifests)

    def refresh_agency(self, agency_slug: str) -> None:
        """Refresh all enabled manifests for a specific agency."""
        # Backwards-compatible API retained; delegate to filtered variant
        self.refresh_agency_for_type(agency_slug, None)

    def refresh_agency_for_type(self, agency_slug: str, report_type: Optional[str]) -> None:
        """Refresh enabled manifests for an agency, optionally filtered by report_type."""
        manifests = self._manifests.get_enabled_manifests_for_agency_and_type(agency_slug, report_type)
        self._refresh_many(manifests)

    def refresh_table(self, table_name: str) -> None:
        """Refresh a single manifest by table name."""
        manifest = self._manifests.get_manifest_by_table(table_name)
        if not manifest:
            logger.warning("No manifest found for table %s", table_name)
            return
        self._refresh_many([manifest])

    def _refresh_many(self, manifests: List[Dict[str, object]]) -> None:
        """Process multiple manifests in parallel.

        Uses fire-and-forget execution so slow queries (20-60 min) don't block
        faster ones. Each task runs independently in the thread pool.
        """
        if not manifests:
            logger.info("No manifests to refresh")
            return

        def on_complete(
            manifest: Dict[str, object],
            result: Optional[None],
            exc: Optional[Exception],
        ) -> None:
            """Callback when a task finishes (success or failure)."""
            table_name = manifest.get("table_name", "<unknown>")
            if exc:
                logger.error("Refresh completed with error for %s: %s", table_name, exc)
            else:
                logger.info("Refresh completed successfully for %s", table_name)

        # Submit tasks in batches to avoid overwhelming the DB with too many
        # queued tasks at once. The thread pool enforces the true concurrency
        # limit (max_workers) while batch submission controls submission rate.
        batch_size = max(1, int(self._config.batch_size))
        start_delay = max(0, int(self._config.start_delay_ms)) / 1000.0

        all_futures = []
        # Create chunks of manifests
        for i in range(0, len(manifests), batch_size):
            chunk = manifests[i : i + batch_size]
            logger.info("Submitting batch %d - %d (size=%d)", i + 1, i + len(chunk), len(chunk))
            # Throttle by checking current active DB queries if configured
            max_active = int(getattr(self._config, "max_db_active_queries", 0))
            if max_active > 0:
                while True:
                    try:
                        active = self._mv.get_active_db_query_count()
                    except Exception:
                        active = 0
                    if active < max_active:
                        break
                    logger.warning("Active DB queries (%d) >= threshold (%d); sleeping 1s before rechecking", active, max_active)
                    time.sleep(1)

            futures = self._executor.submit_all(
                self._refresh_single,
                chunk,
                on_complete=on_complete,
            )
            all_futures.extend(futures)

            if start_delay > 0 and (i + batch_size) < len(manifests):
                logger.debug("Sleeping %.3fs before submitting next batch", start_delay)
                time.sleep(start_delay)

        # Wait for all to complete (we still want the job to wait for everything)
        self._executor.wait_for_all(all_futures)

    def _refresh_single(self, manifest: Dict[str, object]) -> None:
        """Refresh a single manifest entry.

        This method:
        1. Checks if the query has changed; if so, recreates the view
        2. Otherwise refreshes the existing view (CONCURRENTLY if possible)
        3. Creates a unique index if missing (enables concurrent refresh)
        4. Captures PostgreSQL-side statistics
        5. Records history in the seeder tables
        """
        if not self._circuit_breaker.allow():
            logger.error("Circuit open; skipping refresh for %s", manifest.get("table_name"))
            return

        run_id = str(uuid.uuid4())
        table_name = str(manifest["table_name"])
        query = str(manifest["query"])

        self._history.record_start(run_id, manifest)
        started = time.time()

        try:
            # Check if query has changed or view doesn't exist
            needs_recreate = self._mv.query_changed(table_name, query)

            if needs_recreate:
                logger.info("Query changed or view missing for %s; recreating", table_name)
                self._mv.create_or_replace_view(table_name, query)
                # Note: Auto-creation of unique indexes has been intentionally removed
                # because choosing a safe unique key requires domain knowledge.
                # If concurrent refresh is needed, create a proper unique index
                # manually for the materialized view via a migration or DB script.
            else:
                # View exists and query unchanged; refresh it
                # Pass concurrently flag directly to refresh_view; it will handle
                # the fallback to non-concurrent refresh if the view lacks a unique
                # index (PostgreSQL requirement for CONCURRENTLY).
                self._mv.refresh_view(table_name, concurrently=self._config.refresh_concurrently)

            # Update planner statistics
            self._mv.analyze_view(table_name)

            duration = int(time.time() - started)
            view_stats = self._mv.get_view_stats(table_name)

            # Get PostgreSQL-side query statistics instead of Python process stats
            pg_stats = self._get_postgres_query_stats(table_name)

            self._history.record_success(
                run_id,
                manifest,
                duration_seconds=duration,
                records_processed=view_stats.get("row_count", 0),
                bytes_processed=view_stats.get("total_bytes", 0),
                memory_usage_mb=pg_stats.get("shared_blks_mb", 0),
                cpu_percentage=pg_stats.get("cpu_estimate", 0),
            )
            self._circuit_breaker.record_success()

        except Exception as exc:
            logger.exception("Refresh failed for %s", table_name)
            self._circuit_breaker.record_failure()
            self._history.record_error(run_id, manifest, str(exc))

    def _get_postgres_query_stats(self, table_name: str) -> Dict[str, int]:
        """Retrieve PostgreSQL-side query statistics.

        Attempts to get metrics from pg_stat_statements if available.
        Falls back to zeros if the extension is not enabled.
        """
        stats: Dict[str, int] = {
            "shared_blks_mb": 0,
            "cpu_estimate": 0,
            "total_time_ms": 0,
            "rows_affected": 0,
        }

        # Try pg_stat_statements for detailed query metrics
        pg_stmt_stats = self._mv.get_pg_stat_statements_for_query(table_name)
        if pg_stmt_stats:
            # Convert shared blocks to MB (each block is 8KB in PostgreSQL)
            shared_blks = int(pg_stmt_stats.get("shared_blks_hit", 0)) + int(
                pg_stmt_stats.get("shared_blks_read", 0)
            )
            stats["shared_blks_mb"] = (shared_blks * 8) // 1024

            # Total execution time
            stats["total_time_ms"] = int(pg_stmt_stats.get("total_time_ms", 0))

            # Rows affected
            stats["rows_affected"] = int(pg_stmt_stats.get("rows", 0))

            # CPU estimate: ratio of execution time to calls (higher = more CPU intensive)
            calls = int(pg_stmt_stats.get("calls", 1)) or 1
            mean_time = int(pg_stmt_stats.get("mean_time_ms", 0))
            # Rough CPU estimate: normalize mean time to 0-100 scale
            # Queries taking > 60s get high CPU score
            stats["cpu_estimate"] = min(100, int((mean_time / 600) * 100))

        return stats
