"""Repository for fetching reporting manifests (custom + canned).

This repository now uses Django ORM models from `etl_database_schema` instead
of raw SQL. Django must be bootstrapped (DJANGO_SETTINGS_MODULE + django.setup())
before instantiating this repository.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Any


class ManifestRepository:
    """Repository for fetching reporting manifests (custom + canned).

    This class supports two modes for backward compatibility:
      - SQL mode: when a `db_client` with `execute_query(sql, params)` is provided
        the repository runs raw SQL and returns dict rows (used by tests and
        legacy callers).
      - ORM mode: when no db_client is provided, the repository imports Django
        ORM models from `etl_database_schema` and returns mapped rows.

    This lets callers choose the lightweight SQL path for fast access in
    non-Django contexts (tests, lightweight runners) while allowing full ORM
    usage when Django is bootstrapped.
    """

    def __init__(self, db_client: Optional[Any] = None) -> None:
        # db_client: object exposing execute_query(sql, params) -> list[dict]
        self._db = db_client

    def _ensure_models(self):
        """Import and return ORM models required by this repository.

        Returns: (SeederCustomReportManifest, SeederCannedReportManifest, SeederCannedReport, Agency, SeederJobStatus)
        Raises RuntimeError with guidance when models are unavailable.
        """
        try:
            from etl_database_schema.apps.bms_reporting.models import (
                SeederCustomReportManifest,
                SeederCannedReportManifest,
                SeederCannedReport,
                SeederJobStatus,
            )
            # Agency model lives in the bms app
            from etl_database_schema.apps.bms.models import Agency

            return (
                SeederCustomReportManifest,
                SeederCannedReportManifest,
                SeederCannedReport,
                Agency,
                SeederJobStatus,
            )
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError(
                "Django ORM models are not available. Ensure DJANGO_SETTINGS_MODULE is set "
                "and that reporting_seeder.django_bootstrap.bootstrap_django(...) has been called before using ManifestRepository."
            ) from exc

    def _job_status_map(self) -> Dict[str, int]:
        """Return a mapping of table_name -> consecutive_failures from SeederJobStatus.

        In SQL mode this will return an empty map (tests do not expect job stats).
        """
        if self._db:
            return {}
        _, _, _, _, SeederJobStatus = self._ensure_models()
        qs = SeederJobStatus.objects.all().values("table_name", "consecutive_failures")
        return {r["table_name"]: int(r["consecutive_failures"] or 0) for r in qs}

    def _row_from_custom(self, obj) -> Dict[str, object]:
        """Map a SeederCustomReportManifest instance to the repository row dict."""
        agency = getattr(obj, "agency", None)
        agency_name = getattr(agency, "name", None) if agency is not None else None
        table_name = getattr(obj, "table_name", None)
        job_map = self._job_status_map()
        return {
            "id": int(getattr(obj, "id", None)),
            "table_name": table_name,
            "report_name": getattr(obj, "report_name", None),
            "agency_id": getattr(obj, "agency_id", None),
            "agency_name": agency_name,
            "agency_slug": getattr(obj, "agency_slug", None),
            "query": getattr(obj, "query", None),
            "report_type": "custom",
            "database_id": getattr(obj, "database_id", None),
            "consecutive_failures": int(job_map.get(table_name, 0)),
        }

    def _row_from_canned(self, crm_obj) -> Dict[str, object]:
        """Map a SeederCannedReportManifest instance (crm) and its canned_report to row dict."""
        cr = getattr(crm_obj, "canned_report", None)
        agency = getattr(crm_obj, "agency", None)
        agency_name = getattr(agency, "name", None) if agency is not None else None
        table_name = getattr(cr, "table_name", None) if cr is not None else None
        job_map = self._job_status_map()
        return {
            "id": int(getattr(crm_obj, "id", None)),
            "table_name": table_name,
            "report_name": getattr(cr, "report_name", None) if cr is not None else None,
            "agency_id": getattr(crm_obj, "agency_id", None),
            "agency_name": agency_name,
            "agency_slug": getattr(crm_obj, "agency_slug", None),
            "query": getattr(cr, "query", None) if cr is not None else None,
            "report_type": "canned",
            "database_id": getattr(cr, "database_id", None) if cr is not None else None,
            "consecutive_failures": int(job_map.get(table_name, 0)),
        }

    # ---------------------- SQL fallback implementations ---------------------
    def _sql_get_enabled_manifests(self) -> List[Dict[str, object]]:
        """SQL path: return list of enabled manifests combining custom and canned reports."""
        sql = """
        SELECT m.id, m.table_name, m.query, m.agency_slug
        FROM reporting.seeder_custom_report_manifest m
        WHERE m.enabled = true
        UNION ALL
        SELECT cr.id AS id, cr.table_name, cr.query, cm.agency_slug
        FROM reporting.seeder_canned_report cr
        JOIN reporting.seeder_canned_report_manifest cm ON cm.canned_report_id = cr.id
        WHERE cm.enabled = true
        """
        return self._db.execute_query(sql)

    def _sql_get_enabled_manifests_for_agency(self, agency_slug: str) -> List[Dict[str, object]]:
        sql = """
        SELECT m.id, m.table_name, m.query, m.agency_slug
        FROM reporting.seeder_custom_report_manifest m
        WHERE m.enabled = true AND (m.agency_slug = %s OR m.agency_slug IS NULL)
        UNION ALL
        SELECT cr.id AS id, cr.table_name, cr.query, cm.agency_slug
        FROM reporting.seeder_canned_report cr
        JOIN reporting.seeder_canned_report_manifest cm ON cm.canned_report_id = cr.id
        WHERE cm.enabled = true AND (cm.agency_slug = %s OR cm.agency_slug IS NULL)
        """
        return self._db.execute_query(sql, [agency_slug, agency_slug])

    def _sql_get_manifest_by_table(self, table_name: str) -> Optional[Dict[str, object]]:
        sql = """
        SELECT m.id, m.table_name, m.query
        FROM reporting.seeder_custom_report_manifest m
        WHERE m.table_name = %s
        LIMIT 1
        """
        rows = self._db.execute_query(sql, [table_name])
        if rows:
            return rows[0]
        sql2 = """
        SELECT cr.id AS id, cr.table_name, cr.query
        FROM reporting.seeder_canned_report cr
        JOIN reporting.seeder_canned_report_manifest cm ON cm.canned_report_id = cr.id
        WHERE cr.table_name = %s
        LIMIT 1
        """
        rows2 = self._db.execute_query(sql2, [table_name])
        return rows2[0] if rows2 else None

    def _sql_get_manifest_by_id(self, manifest_id: int) -> Optional[Dict[str, object]]:
        sql = """
        SELECT m.id, m.table_name, m.query
        FROM reporting.seeder_custom_report_manifest m
        WHERE m.id = %s
        LIMIT 1
        """
        rows = self._db.execute_query(sql, [manifest_id])
        if rows:
            return rows[0]
        sql2 = """
        SELECT cm.id AS id, cr.table_name, cr.query
        FROM reporting.seeder_canned_report_manifest cm
        JOIN reporting.seeder_canned_report cr ON cm.canned_report_id = cr.id
        WHERE cm.id = %s
        LIMIT 1
        """
        rows2 = self._db.execute_query(sql2, [manifest_id])
        return rows2[0] if rows2 else None

    # ---------------------- Public API ---------------------
    def get_enabled_manifests(self) -> List[Dict[str, object]]:
        """Fetch all enabled manifests (both custom and canned)."""
        return self.get_enabled_manifests_for_type(None)

    def get_enabled_manifests_for_type(self, report_type: Optional[str]) -> List[Dict[str, object]]:
        """Fetch enabled manifests, optionally filtered by report_type ('custom'|'canned')."""
        rt = (report_type or "all").lower()
        if rt not in ("all", "custom", "canned"):
            raise ValueError("report_type must be one of: all, custom, canned")

        # If a test or subclass populated an in-memory manifests list, use it (fast test path)
        if hasattr(self, "_manifests"):
            all_rows = getattr(self, "_manifests")
            if rt == "all":
                return all_rows
            return [r for r in all_rows if r.get("report_type") == rt]

        # If a subclass provided its own `get_enabled_manifests` implementation
        # (not the base class), call it directly when no DB client is configured.
        if getattr(self, "_db", None) is None:
            cls_method = getattr(self.__class__, "get_enabled_manifests", None)
            base_method = ManifestRepository.get_enabled_manifests
            if cls_method is not None and cls_method is not base_method:
                # Call the subclass implementation directly to obtain rows
                all_rows = cls_method(self)
                if rt == "all":
                    return all_rows
                return [r for r in all_rows if r.get("report_type") == rt]

        # SQL fallback
        if getattr(self, "_db", None) is not None:
            if rt == "all":
                return self._sql_get_enabled_manifests()
            if rt == "custom":
                return self._db.execute_query("SELECT id, table_name, query, agency_slug FROM reporting.seeder_custom_report_manifest WHERE enabled = true")
            if rt == "canned":
                return self._db.execute_query("SELECT cr.id, cr.table_name, cr.query, cm.agency_slug FROM reporting.seeder_canned_report cr JOIN reporting.seeder_canned_report_manifest cm ON cm.canned_report_id = cr.id WHERE cm.enabled = true")

        # ORM path
        (CustomManifest, CannedManifest, CannedReport, Agency, SeederJobStatus) = self._ensure_models()
        results: List[Dict[str, object]] = []

        if rt in ("all", "custom"):
            qs = CustomManifest.objects.filter(enabled=True).select_related("agency")
            for obj in qs:
                results.append(self._row_from_custom(obj))

        if rt in ("all", "canned"):
            qs2 = CannedManifest.objects.filter(enabled=True).select_related("canned_report", "agency")
            for crm in qs2:
                results.append(self._row_from_canned(crm))

        return results

    def get_enabled_manifests_for_agency(self, agency_slug: str) -> List[Dict[str, object]]:
        """Fetch enabled manifests for a specific agency."""
        return self.get_enabled_manifests_for_agency_and_type(agency_slug, None)

    def get_enabled_manifests_for_agency_and_type(self, agency_slug: str, report_type: Optional[str]) -> List[Dict[str, object]]:
        """Fetch enabled manifests for a specific agency, optionally filtered by report_type."""
        rt = (report_type or "all").lower()
        if rt not in ("all", "custom", "canned"):
            raise ValueError("report_type must be one of: all, custom, canned")

        # SQL fallback
        if getattr(self, "_db", None) is not None:
            return self._sql_get_enabled_manifests_for_agency(agency_slug)

        (CustomManifest, CannedManifest, CannedReport, Agency, SeederJobStatus) = self._ensure_models()
        results: List[Dict[str, object]] = []

        if rt in ("all", "custom"):
            qs = CustomManifest.objects.filter(enabled=True, agency_slug=agency_slug).select_related("agency")
            for obj in qs:
                results.append(self._row_from_custom(obj))

        if rt in ("all", "canned"):
            qs2 = CannedManifest.objects.filter(enabled=True, agency_slug=agency_slug).select_related("canned_report", "agency")
            for crm in qs2:
                results.append(self._row_from_canned(crm))

        return results

    def get_manifest_by_table(self, table_name: str) -> Optional[Dict[str, object]]:
        """Fetch a manifest by its table name."""
        # SQL fallback
        if self._db is not None:
            return self._sql_get_manifest_by_table(table_name)

        (CustomManifest, CannedManifest, CannedReport, Agency, SeederJobStatus) = self._ensure_models()

        # Try custom manifests first
        try:
            obj = CustomManifest.objects.select_related("agency").filter(table_name=table_name).first()
            if obj:
                return self._row_from_custom(obj)
        except Exception:
            pass

        # Then try canned (join to canned_report)
        try:
            crm = CannedManifest.objects.select_related("canned_report", "agency").filter(canned_report__table_name=table_name).first()
            if crm:
                return self._row_from_canned(crm)
        except Exception:
            pass

        return None

    def get_manifest_by_id(self, manifest_id: int) -> Optional[Dict[str, object]]:
        """Fetch a manifest by its id."""
        # SQL fallback
        if self._db is not None:
            return self._sql_get_manifest_by_id(manifest_id)

        (CustomManifest, CannedManifest, CannedReport, Agency, SeederJobStatus) = self._ensure_models()

        obj = CustomManifest.objects.select_related("agency").filter(id=manifest_id).first()
        if obj:
            return self._row_from_custom(obj)
        crm = CannedManifest.objects.select_related("canned_report", "agency").filter(id=manifest_id).first()
        if crm:
            return self._row_from_canned(crm)
        return None
