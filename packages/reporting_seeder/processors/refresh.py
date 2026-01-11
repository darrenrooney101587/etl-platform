"""Processor to refresh reporting materialized views with concurrency and circuit breaking."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Dict, List
import psutil

from etl_core.support.circuit_breaker import CircuitBreaker
from etl_core.support.executor import ParallelExecutor
from reporting_seeder.repositories.history import HistoryRepository
from reporting_seeder.repositories.manifests import ManifestRepository
from reporting_seeder.repositories.materialized_views import MaterializedViewRepository
from reporting_seeder.services.config import SeederConfig

logger = logging.getLogger(__name__)


class RefreshProcessor:
    """Orchestrates concurrent refresh of manifest-driven materialized views."""

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
        manifests = self._manifests.get_enabled_manifests()
        self._refresh_many(manifests)

    def refresh_agency(self, agency_slug: str) -> None:
        manifests = self._manifests.get_enabled_manifests_for_agency(agency_slug)
        self._refresh_many(manifests)

    def refresh_table(self, table_name: str) -> None:
        manifest = self._manifests.get_manifest_by_table(table_name)
        if not manifest:
            logger.warning("No manifest found for table %s", table_name)
            return
        self._refresh_many([manifest])

    def _refresh_many(self, manifests: List[Dict[str, object]]) -> None:
        if not manifests:
            logger.info("No manifests to refresh")
            return

        def _run(manifest: Dict[str, object]) -> None:
            if not self._circuit_breaker.allow():
                logger.error("Circuit open; skipping remaining refreshes")
                return

            process = psutil.Process()
            # Prime CPU counter
            process.cpu_percent(interval=None)

            run_id = str(uuid.uuid4())
            self._history.record_start(run_id, manifest)
            started = time.time()
            try:
                table_name = str(manifest["table_name"])
                query = str(manifest["query"])
                if self._config.refresh_concurrently and self._mv.view_exists(table_name):
                    self._mv.refresh_view(table_name)
                else:
                    self._mv.create_or_replace_view(table_name, query)
                self._mv.analyze_view(table_name)

                duration = int(time.time() - started)
                view_stats = self._mv.get_view_stats(table_name)

                mem_mb = int(process.memory_info().rss / 1024 / 1024)
                cpu_pct = int(process.cpu_percent(interval=None))

                self._history.record_success(
                    run_id,
                    manifest,
                    duration_seconds=duration,
                    records_processed=view_stats.get("row_count", 0),
                    bytes_processed=view_stats.get("total_bytes", 0),
                    memory_usage_mb=mem_mb,
                    cpu_percentage=cpu_pct,
                )
                self._circuit_breaker.record_success()
            except Exception as exc:
                logger.exception("Refresh failed for %s", manifest.get("table_name"))
                self._circuit_breaker.record_failure()
                self._history.record_error(run_id, manifest, str(exc))

        self._executor.map(_run, manifests)
