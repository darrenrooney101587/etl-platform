"""Repository for fetching reporting manifests (custom + canned)."""

from __future__ import annotations

from typing import Dict, List, Optional

from etl_core.database.client import DatabaseClient


class ManifestRepository:
    """Repository for fetching reporting manifests (custom + canned)."""

    def __init__(self, db_client: DatabaseClient) -> None:
        self._db = db_client

    def get_enabled_manifests(self) -> List[Dict[str, object]]:
        """Fetch all enabled manifests."""
        sql = """
        SELECT m.id,
               m.table_name,
               m.report_name,
               m.agency_id,
               a.name AS agency_name,
               m.agency_slug,
               m.query,
               'custom' AS report_type,
               m.database_id,
               COALESCE(s.consecutive_failures, 0) AS consecutive_failures
        FROM reporting.seeder_custom_report_manifest m
        JOIN public.agency a ON a.id = m.agency_id
        LEFT JOIN reporting.seeder_job_status s ON s.table_name = m.table_name
        WHERE m.enabled = TRUE
        UNION ALL
        SELECT crm.id,
               cr.table_name,
               cr.report_name,
               crm.agency_id,
               a.name AS agency_name,
               crm.agency_slug,
               cr.query,
               'canned' AS report_type,
               cr.database_id,
               COALESCE(s.consecutive_failures, 0) AS consecutive_failures
        FROM reporting.seeder_canned_report_manifest crm
                 JOIN reporting.seeder_canned_report cr ON cr.id = crm.canned_report_id
                 JOIN public.agency a ON a.id = crm.agency_id
                 LEFT JOIN reporting.seeder_job_status s ON s.table_name = cr.table_name
        """
        return self._db.execute_query(sql)

    def get_enabled_manifests_for_agency(self, agency_slug: str) -> List[Dict[str, object]]:
        """Fetch enabled manifests for a specific agency."""
        sql = """
        SELECT m.id,
               m.table_name,
               m.report_name,
               m.agency_id,
               a.name AS agency_name,
               m.agency_slug,
               m.query,
               'custom' AS report_type,
               m.database_id,
               COALESCE(s.consecutive_failures, 0) AS consecutive_failures
        FROM reporting.seeder_custom_report_manifest m
        JOIN public.agency a ON a.id = m.agency_id
        LEFT JOIN reporting.seeder_job_status s ON s.table_name = m.table_name
        WHERE m.enabled = TRUE
          AND m.agency_slug = %s
        UNION ALL
        SELECT crm.id,
               cr.table_name,
               cr.report_name,
               crm.agency_id,
               a.name AS agency_name,
               crm.agency_slug,
               cr.query,
               'canned' AS report_type,
               cr.database_id,
               COALESCE(s.consecutive_failures, 0) AS consecutive_failures
        FROM reporting.seeder_canned_report_manifest crm
                 JOIN reporting.seeder_canned_report cr ON cr.id = crm.canned_report_id
                 JOIN public.agency a ON a.id = crm.agency_id
                 LEFT JOIN reporting.seeder_job_status s ON s.table_name = cr.table_name
        WHERE crm.agency_slug = %s
        """
        return self._db.execute_query(sql, [agency_slug, agency_slug])

    def get_manifest_by_table(self, table_name: str) -> Optional[Dict[str, object]]:
        """Fetch a manifest by its table name."""
        sql = """
        SELECT m.id,
               m.table_name,
               m.report_name,
               m.agency_id,
               a.name AS agency_name,
               m.agency_slug,
               m.query,
               'custom' AS report_type,
               m.database_id,
               COALESCE(s.consecutive_failures, 0) AS consecutive_failures
        FROM reporting.seeder_custom_report_manifest m
        JOIN public.agency a ON a.id = m.agency_id
        LEFT JOIN reporting.seeder_job_status s ON s.table_name = m.table_name
        WHERE m.table_name = %s
        UNION ALL
        SELECT crm.id,
               cr.table_name,
               cr.report_name,
               crm.agency_id,
               a.name AS agency_name,
               crm.agency_slug,
               cr.query,
               'canned' AS report_type,
               cr.database_id,
               COALESCE(s.consecutive_failures, 0) AS consecutive_failures
        FROM reporting.seeder_canned_report_manifest crm
                 JOIN reporting.seeder_canned_report cr ON cr.id = crm.canned_report_id
                 JOIN public.agency a ON a.id = crm.agency_id
                 LEFT JOIN reporting.seeder_job_status s ON s.table_name = cr.table_name
        WHERE cr.table_name = %s
        LIMIT 1
        """
        rows = self._db.execute_query(sql, [table_name, table_name])
        return rows[0] if rows else None
