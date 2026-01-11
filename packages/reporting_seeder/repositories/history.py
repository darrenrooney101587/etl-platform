"""Repository for recording refresh history and metrics."""

from __future__ import annotations

from typing import Any, Dict, List

from packages.etl_core.database.client import DatabaseClient


class HistoryRepository:
    def __init__(self, db_client: DatabaseClient) -> None:
        self._db = db_client

    def record_start(self, run_id: str, manifest: Dict[str, object]) -> None:
        manifest_id = int(manifest["id"])
        # Insert history
        sql_history = """
        INSERT INTO reporting.seeder_run_history (
            run_id, manifest_id, table_name, report_name, agency_id, agency_slug, report_type,
            status, start_time, consecutive_failures
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'running', now(), COALESCE(%s, 0))
        """
        self._db.execute_query(
            sql_history,
            [
                run_id,
                manifest_id,
                manifest.get("table_name"),
                manifest.get("report_name"),
                manifest.get("agency_id"),
                manifest.get("agency_slug"),
                manifest.get("report_type"),
                manifest.get("consecutive_failures", 0),
            ],
        )

        # Upsert status
        sql_status = """
        INSERT INTO reporting.seeder_job_status (
            manifest_id, table_name, report_name, report_type, agency_id, agency_slug,
            status, start_time, last_run_id, consecutive_failures, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'running', now(), %s, COALESCE(%s, 0), now())
        ON CONFLICT (table_name) DO UPDATE SET
            status = EXCLUDED.status,
            start_time = EXCLUDED.start_time,
            last_run_id = EXCLUDED.last_run_id,
            updated_at = EXCLUDED.updated_at
        """
        self._db.execute_query(
            sql_status,
            [
                manifest_id,
                manifest.get("table_name"),
                manifest.get("report_name"),
                manifest.get("report_type"),
                manifest.get("agency_id"),
                manifest.get("agency_slug"),
                run_id,
                manifest.get("consecutive_failures", 0),
            ],
        )

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
        manifest_id = int(manifest["id"])
        # Update history
        sql_history = """
        UPDATE reporting.seeder_run_history
        SET status = 'success',
            finish_time = now(),
            duration_seconds = %s,
            records_processed = %s,
            bytes_processed = %s,
            memory_usage_mb = %s,
            cpu_percentage = %s,
            consecutive_failures = 0
        WHERE run_id = %s AND manifest_id = %s
        """
        self._db.execute_query(
            sql_history,
            [
                duration_seconds,
                records_processed,
                bytes_processed,
                memory_usage_mb,
                cpu_percentage,
                run_id,
                manifest_id,
            ],
        )

        # Update status
        sql_status = """
        UPDATE reporting.seeder_job_status
        SET status = 'success',
            duration_seconds = %s,
            consecutive_failures = 0,
            last_errors = NULL,
            updated_at = now()
        WHERE table_name = %s
        """
        self._db.execute_query(sql_status, [duration_seconds, manifest.get("table_name")])

    def record_error(self, run_id: str, manifest: Dict[str, object], errors: str) -> None:
        manifest_id = int(manifest["id"])
        # Update history
        sql_history = """
        UPDATE reporting.seeder_run_history
        SET status = 'error',
            finish_time = now(),
            errors = %s,
            consecutive_failures = COALESCE(consecutive_failures, 0) + 1
        WHERE run_id = %s AND manifest_id = %s
        """
        self._db.execute_query(sql_history, [errors, run_id, manifest_id])

        # Update status
        sql_status = """
        UPDATE reporting.seeder_job_status
        SET status = 'error',
            consecutive_failures = COALESCE(consecutive_failures, 0) + 1,
            last_errors = %s,
            updated_at = now()
        WHERE table_name = %s
        """
        self._db.execute_query(sql_status, [errors, manifest.get("table_name")])

    def list_recent_runs(self, limit: int = 100) -> List[Dict[str, Any]]:
        sql = """
        SELECT run_id,
               manifest_id,
               status,
               start_time,
               finish_time,
               duration_seconds,
               records_processed,
               bytes_processed,
               memory_usage_mb,
               cpu_percentage,
               errors
        FROM reporting.seeder_run_history
        ORDER BY start_time DESC
        LIMIT %s
        """
        return self._db.execute_query(sql, [limit])
