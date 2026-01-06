"""Repository layer for data quality pipeline database operations.

This repository handles all database interactions for the data quality pipeline,
including monitoring file lookups, run creation/upserts, and quality result persistence.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from etl_core.database.client import DatabaseClient
from file_processing.models.monitoring import (
    MonitoringFile,
    MonitoringFileDataProfile,
    MonitoringFileDataQuality,
    MonitoringFileRun,
    MonitoringFileSchemaDefinition,
)

logger = logging.getLogger(__name__)


class MonitoringRepository:
    """Repository for monitoring file and data quality database operations.

    This repository contains all domain SQL for the data quality pipeline.
    It accepts a DatabaseClient via constructor injection for testability.
    """

    def __init__(self, db: DatabaseClient) -> None:
        """Initialize the repository.

        Args:
            db: DatabaseClient instance for executing queries.
        """
        self._db = db

    # -------------------------------------------------------------------------
    # MonitoringFile operations
    # -------------------------------------------------------------------------

    def get_monitoring_file(
        self,
        agency_slug: str,
        file_name: str,
    ) -> Optional[MonitoringFile]:
        """Look up a monitoring file by agency slug and file name.

        Args:
            agency_slug: The S3 agency slug (from the object key).
            file_name: The file name (from the object key).

        Returns:
            MonitoringFile if found, None otherwise.
        """
        # Resolve internal BMS ID or slug using ref_agency_designations mapping if possible
        environment = (os.getenv("ENVIRONMENT", "prod") or "prod").strip().lower()

        # Normalize common synonyms so callers can set ENVIRONMENT="production" or "prod"
        if environment in ("production", "prod", "prod-etl", "prod_etl", "production-etl"):
            environment = "prod"

        # Allowed environments
        allowed = ("prod", "qa", "sandbox")
        if environment not in allowed:
            # Fallback to prod for any unknown/typo value to be conservative in production behavior
            environment = "prod"

        # Try to find an agency mapping using ref_agency_designations
        # We look up by {env}_s3_slug = agency_slug provided
        cols = f"{environment}_bms_slug, {environment}_bms_id"
        mapping_sql = f"""
            SELECT {cols}
            FROM reporting.ref_agency_designations
            WHERE {environment}_s3_slug = %s
        """
        mapping_rows = self._db.execute_query(mapping_sql, [agency_slug])

        internal_slug = agency_slug
        bms_id: Optional[int] = None
        # TODO: If monitoring_file used agency_id, we would use bms_id here.
        # Currently the MonitoringFile logic used agency_slug string; prefer agency_id when mapping exists.
        if mapping_rows:
            mapped = mapping_rows[0]
            # Map both slug and id if present
            bms_slug = mapped.get(f"{environment}_bms_slug")
            mapped_bms_id = mapped.get(f"{environment}_bms_id")
            if bms_slug:
                internal_slug = bms_slug
            if mapped_bms_id:
                try:
                    bms_id = int(mapped_bms_id)
                except Exception:
                    # keep bms_id as None if conversion fails
                    bms_id = None

        # 1. If we resolved a BMS id, prefer lookup by agency_id + file_name
        if bms_id is not None:
            sql = """
                SELECT
                    mf.id,
                    mf.file_name,
                    mf.agency_slug,
                    mf.latest_data_quality_score,
                    mf.schema_definition_id,
                    mf.s3_url,
                    mf.is_suppressed
                FROM reporting.monitoring_file mf
                WHERE mf.agency_id = %s
                  AND mf.file_name = %s
            """
            rows = self._db.execute_query(sql, [bms_id, file_name])
        else:
            sql = """
                SELECT
                    mf.id,
                    mf.file_name,
                    mf.agency_slug,
                    mf.latest_data_quality_score,
                    mf.schema_definition_id,
                    mf.s3_url,
                    mf.is_suppressed
                FROM reporting.monitoring_file mf
                WHERE lower(mf.agency_slug) = lower(%s)
                  AND mf.file_name = %s
            """
            rows = self._db.execute_query(sql, [internal_slug, file_name])

        if not rows:
            # 2. If valid lookup failed, try falling back to the original S3 slug
            # (in case no mapping existed or monitoring_file uses S3 slug directly)
            # If we previously tried by agency_id, switch to slug-based lookup now.
            if bms_id is not None:
                slug_sql = """
                    SELECT
                        mf.id,
                        mf.file_name,
                        mf.agency_slug,
                        mf.latest_data_quality_score,
                        mf.schema_definition_id,
                        mf.s3_url,
                        mf.is_suppressed
                    FROM reporting.monitoring_file mf
                    WHERE lower(mf.agency_slug) = lower(%s)
                      AND mf.file_name = %s
                """
                rows = self._db.execute_query(slug_sql, [agency_slug, file_name])
            else:
                if internal_slug != agency_slug:
                    rows = self._db.execute_query(sql, [agency_slug, file_name])

        if not rows:
            # 3. Fallback: try to find by file_name only (dev/stub convenience)
            try:
                fallback_sql = """
                    SELECT
                        mf.id,
                        mf.file_name,
                        mf.agency_slug,
                        mf.latest_data_quality_score,
                        mf.schema_definition_id,
                        mf.s3_url,
                        mf.is_suppressed
                    FROM reporting.monitoring_file mf
                    WHERE mf.file_name = %s
                    ORDER BY mf.id DESC
                    LIMIT 1
                """
                fallback_rows = self._db.execute_query(fallback_sql, [file_name])
                if fallback_rows:
                    row = fallback_rows[0]
                    # Log warning but return the found record
                    logger.warning(
                        "No monitoring_file for agency=%s (internal=%s) file=%s; falling back to file_name-only match id=%s agency=%s",
                        agency_slug,
                        internal_slug,
                        file_name,
                        row.get("id"),
                        row.get("agency_slug"),
                    )
                    return MonitoringFile(
                        id=row["id"],
                        file_name=row["file_name"],
                        agency_slug=row["agency_slug"],
                        latest_data_quality_score=row.get("latest_data_quality_score"),
                        schema_definition_id=row.get("schema_definition_id"),
                        is_suppressed=row.get("is_suppressed", False),
                    )
            except Exception:
                logger.exception("Fallback lookup by file_name failed")
                return None

            return None

        row = rows[0]
        # Check for s3_url match if available?
        # The user requested: "take the agency_id and the event key and query the s3_url for a match."
        # Since we don't have agency_id in this context easily (we have slugs), we can try to validate s3_url
        # if multiple records were returned - but here we select by slug+filename which should be unique?
        # If necessary we could fetch multiple and filter by s3_url suffix match.

        return MonitoringFile(
            id=row["id"],
            file_name=row["file_name"],
            agency_slug=row["agency_slug"],
            latest_data_quality_score=row.get("latest_data_quality_score"),
            schema_definition_id=row.get("schema_definition_id"),
            is_suppressed=row.get("is_suppressed", False),
        )

    def get_monitoring_file_by_id(self, monitoring_file_id: int) -> Optional[MonitoringFile]:
        """Look up a monitoring file by ID.

        Args:
            monitoring_file_id: The monitoring file ID.

        Returns:
            MonitoringFile if found, None otherwise.
        """
        sql = """
            SELECT
                mf.id,
                mf.file_name,
                mf.agency_slug,
                mf.latest_data_quality_score,
                mf.schema_definition_id
            FROM reporting.monitoring_file mf
            WHERE mf.id = %s
        """
        rows = self._db.execute_query(sql, [monitoring_file_id])

        if not rows:
            return None

        row = rows[0]
        return MonitoringFile(
            id=row["id"],
            file_name=row["file_name"],
            agency_slug=row["agency_slug"],
            latest_data_quality_score=row.get("latest_data_quality_score"),
            schema_definition_id=row.get("schema_definition_id"),
        )

    def _get_required_columns_with_no_default(
        self, table_schema: str, table_name: str, exclude: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Return list of columns that are NOT NULL and have no default.

        Each item is a dict: {"column_name": str, "data_type": str}
        """
        exclude = exclude or []
        sql = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
              AND is_nullable = 'NO'
              AND column_default IS NULL
        """
        rows = self._db.execute_query(sql, [table_schema, table_name])
        return [r for r in rows if r["column_name"] not in exclude]

    def _default_for_data_type(self, data_type: str) -> Any:
        """Return a reasonable default value for a SQL data_type string."""
        dt = (data_type or "").lower()
        if "int" in dt:
            return 0
        if "timestamp" in dt or "date" in dt:
            return None  # will use NOW() handling in SQL if needed
        if "json" in dt or "jsonb" in dt or "array" in dt:
            return "{}"
        if "bool" in dt:
            return False
        # fallback to empty string
        return ""

    def create_monitoring_file(
        self,
        agency_slug: str,
        file_name: str,
        schema_definition_id: Optional[int] = None,
        s3_url: Optional[str] = None,
    ) -> MonitoringFile:
        """Create a new monitoring file record.

        Args:
            agency_slug: The agency slug identifier.
            file_name: The file name identifier.
            schema_definition_id: Optional schema definition FK.
            s3_url: Optional S3 URL or path for the file (populates not-null s3_url column if required).

        Returns:
            The created MonitoringFile.
        """
        # base values we always want to set
        base_cols: Dict[str, Any] = {
            "s3_url": s3_url or "",
            "agency_slug": agency_slug,
            "file_name": file_name,
            "schema_definition_id": schema_definition_id,
        }

        # Discover additional NOT NULL columns without default and populate placeholders
        required = self._get_required_columns_with_no_default(
            "reporting", "monitoring_file", exclude=list(base_cols.keys())
        )

        for r in required:
            col = r["column_name"]
            default = self._default_for_data_type(r.get("data_type"))
            # if timestamp/date and default is None, use SQL NOW() by marking special
            base_cols[col] = default

        # Build parametrized insert dynamically
        cols = ", ".join(base_cols.keys())
        placeholders = ", ".join(["%s"] * len(base_cols))
        sql = f"""
            INSERT INTO reporting.monitoring_file ({cols})
            VALUES ({placeholders})
            RETURNING id, file_name, agency_slug, latest_data_quality_score, schema_definition_id
        """
        params = []
        for k in base_cols.keys():
            params.append(base_cols[k])

        rows = self._db.execute_query(sql, params)
        row = rows[0]

        # Defensive fallback: if RETURNING didn't provide an id for any reason,
        # attempt to look up the row we just inserted by (agency_slug, file_name).
        if not row.get("id"):
            logger.warning("INSERT into reporting.monitoring_file did not return an id; falling back to SELECT lookup")
            lookup_rows = self._db.execute_query(
                "SELECT id, file_name, agency_slug, latest_data_quality_score, schema_definition_id "
                "FROM reporting.monitoring_file WHERE agency_slug = %s AND file_name = %s ORDER BY id DESC LIMIT 1",
                [agency_slug, file_name],
            )
            if lookup_rows:
                row = lookup_rows[0]

        return MonitoringFile(
            id=row["id"],
            file_name=row["file_name"],
            agency_slug=row["agency_slug"],
            latest_data_quality_score=row.get("latest_data_quality_score"),
            schema_definition_id=row.get("schema_definition_id"),
        )

    def update_monitoring_file_score(
        self,
        monitoring_file_id: int,
        score: int,
    ) -> None:
        """Update the latest data quality score on a monitoring file.

        Args:
            monitoring_file_id: The monitoring file ID.
            score: The new score to set.
        """
        sql = """
            UPDATE reporting.monitoring_file
            SET latest_data_quality_score = %s
            WHERE id = %s
        """
        self._db.execute_query(sql, [score, monitoring_file_id])

    # -------------------------------------------------------------------------
    # MonitoringFileSchemaDefinition operations
    # -------------------------------------------------------------------------

    def get_schema_definition(
        self,
        schema_definition_id: int,
    ) -> Optional[MonitoringFileSchemaDefinition]:
        """Look up a schema definition by ID.

        Args:
            schema_definition_id: The schema definition ID.

        Returns:
            MonitoringFileSchemaDefinition if found, None otherwise.
        """
        sql = """
            SELECT
                id,
                name,
                description,
                definition,
                created_at,
                updated_at
            FROM reporting.monitoring_file_schema_definition
            WHERE id = %s
        """
        rows = self._db.execute_query(sql, [schema_definition_id])

        if not rows:
            return None

        row = rows[0]
        return MonitoringFileSchemaDefinition(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            definition=row.get("definition") or {},
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    # -------------------------------------------------------------------------
    # MonitoringFileRun operations
    # -------------------------------------------------------------------------

    def get_or_create_run(
        self,
        monitoring_file_id: int,
        run_date: date,
        run_hour: int,
        agency_id: Optional[int] = None,
        file_last_modified: Optional[datetime] = None,
        file_size: Optional[int] = None,
    ) -> MonitoringFileRun:
        """Get or create a monitoring file run with idempotent upsert.

        Uses SELECT ... FOR UPDATE to ensure only one run exists per
        (monitoring_file_id, run_date, run_hour) combination.

        Args:
            monitoring_file_id: The monitoring file ID.
            run_date: The run date.
            run_hour: The run hour (0-23).
            agency_id: Optional agency ID.
            file_last_modified: Optional file last modified timestamp.
            file_size: Optional file size in bytes.

        Returns:
            The existing or newly created MonitoringFileRun.
        """
        # Try to find existing run
        sql_select = """
            SELECT
                id,
                monitoring_file_id,
                agency_id,
                created_at,
                updated_at,
                file_last_modified,
                file_range_lower_limit,
                file_size,
                run_date,
                run_hour
            FROM reporting.monitoring_file_run
            WHERE monitoring_file_id = %s
              AND run_date = %s
              AND run_hour = %s
            FOR UPDATE
        """
        rows = self._db.execute_query(
            sql_select, [monitoring_file_id, run_date, run_hour]
        )

        if rows:
            row = rows[0]
            run = MonitoringFileRun(
                id=row["id"],
                monitoring_file_id=row["monitoring_file_id"],
                run_date=row["run_date"],
                run_hour=row["run_hour"],
                agency_id=row.get("agency_id"),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
                file_last_modified=row.get("file_last_modified"),
                file_range_lower_limit=row.get("file_range_lower_limit"),
                file_size=row.get("file_size"),
            )

            # Update file metadata if provided
            if file_last_modified is not None or file_size is not None:
                self._update_run_metadata(
                    run.id, file_last_modified, file_size
                )
                run.file_last_modified = file_last_modified or run.file_last_modified
                run.file_size = file_size or run.file_size

            return run

        # Create new run
        # Ensure required NOT NULL columns receive reasonable defaults for local/dev runs
        if file_size is None:
            # Some DB schemas require file_size NOT NULL; default to 0 for created test runs
            file_size = 0

        sql_insert = """
            INSERT INTO reporting.monitoring_file_run
                (monitoring_file_id, run_date, run_hour, agency_id, file_last_modified, file_size)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, monitoring_file_id, agency_id, created_at, updated_at,
                      file_last_modified, file_range_lower_limit, file_size, run_date, run_hour
        """
        rows = self._db.execute_query(
            sql_insert,
            [monitoring_file_id, run_date, run_hour, agency_id, file_last_modified, file_size],
        )
        row = rows[0]

        return MonitoringFileRun(
            id=row["id"],
            monitoring_file_id=row["monitoring_file_id"],
            run_date=row["run_date"],
            run_hour=row["run_hour"],
            agency_id=row.get("agency_id"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            file_last_modified=row.get("file_last_modified"),
            file_range_lower_limit=row.get("file_range_lower_limit"),
            file_size=row.get("file_size"),
        )

    def get_run(
        self,
        monitoring_file_id: int,
        run_date: date,
        run_hour: int,
    ) -> Optional[MonitoringFileRun]:
        """Return an existing MonitoringFileRun or None if not found.

        This method intentionally does not create a run. Run lifecycle is owned
        by an upstream system.
        """
        sql = """
            SELECT
                id,
                monitoring_file_id,
                agency_id,
                created_at,
                updated_at,
                file_last_modified,
                file_range_lower_limit,
                file_size,
                run_date,
                run_hour
            FROM reporting.monitoring_file_run
            WHERE monitoring_file_id = %s
              AND run_date = %s
              AND run_hour = %s
        """
        rows = self._db.execute_query(sql, [monitoring_file_id, run_date, run_hour])
        if not rows:
            return None
        row = rows[0]
        return MonitoringFileRun(
            id=row["id"],
            monitoring_file_id=row["monitoring_file_id"],
            run_date=row["run_date"],
            run_hour=row["run_hour"],
            agency_id=row.get("agency_id"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            file_last_modified=row.get("file_last_modified"),
            file_range_lower_limit=row.get("file_range_lower_limit"),
            file_size=row.get("file_size"),
        )
    #TODO when e migrate over file monitoring from clover we will replace this since THIS system will create the run records
    def get_latest_run(self, monitoring_file_id: int) -> Optional[MonitoringFileRun]:
        """Get the most recent run for a monitoring file.

        Args:
            monitoring_file_id: The monitoring file ID.

        Returns:
            The most recent MonitoringFileRun or None.
        """
        sql = """
            SELECT
                id,
                monitoring_file_id,
                agency_id,
                created_at,
                updated_at,
                file_last_modified,
                file_range_lower_limit,
                file_size,
                run_date,
                run_hour
            FROM reporting.monitoring_file_run
            WHERE monitoring_file_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """
        rows = self._db.execute_query(sql, [monitoring_file_id])
        if not rows:
            return None
        row = rows[0]
        return MonitoringFileRun(
            id=row["id"],
            monitoring_file_id=row["monitoring_file_id"],
            run_date=row["run_date"],
            run_hour=row["run_hour"],
            agency_id=row.get("agency_id"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            file_last_modified=row.get("file_last_modified"),
            file_range_lower_limit=row.get("file_range_lower_limit"),
            file_size=row.get("file_size"),
        )

    def _update_run_metadata(
        self,
        run_id: int,
        file_last_modified: Optional[datetime],
        file_size: Optional[int],
    ) -> None:
        """Update file metadata on an existing run.

        Args:
            run_id: The run ID.
            file_last_modified: New file last modified timestamp.
            file_size: New file size.
        """
        updates: List[str] = ["updated_at = NOW()"]
        params: List[Any] = []

        if file_last_modified is not None:
            updates.append("file_last_modified = %s")
            params.append(file_last_modified)

        if file_size is not None:
            updates.append("file_size = %s")
            params.append(file_size)

        params.append(run_id)

        sql = f"""
            UPDATE reporting.monitoring_file_run
            SET {', '.join(updates)}
            WHERE id = %s
        """
        self._db.execute_query(sql, params)

    # -------------------------------------------------------------------------
    # MonitoringFileDataQuality operations
    # -------------------------------------------------------------------------

    def upsert_data_quality(
        self,
        monitoring_file_run_id: int,
        monitoring_file_id: Optional[int],
        score: int,
        passed: bool,
        metrics: Dict[str, Any],
        deductions: Dict[str, float],
        failed_validation_message: Optional[str] = None,
        failed_validation_rules: Optional[List[Dict[str, Any]]] = None,
    ) -> MonitoringFileDataQuality:
        """Upsert a data quality record for a run.

        Uses INSERT ... ON CONFLICT for idempotent upsert.

        Args:
            monitoring_file_run_id: The run ID.
            monitoring_file_id: Optional monitoring file ID.
            score: Computed quality score (0-100).
            passed: Whether the quality check passed.
            metrics: Metrics JSON payload.
            deductions: Deductions JSON payload.
            failed_validation_message: Optional failure message.
            failed_validation_rules: Optional list of failed rules.

        Returns:
            The upserted MonitoringFileDataQuality.
        """
        import json

        sql = """
            INSERT INTO reporting.monitoring_file_data_quality
                (monitoring_file_run_id, monitoring_file_id, score, passed, metrics, deductions,
                 failed_validation_message, failed_validation_rules, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (monitoring_file_run_id)
            DO UPDATE SET
                monitoring_file_id = EXCLUDED.monitoring_file_id,
                score = EXCLUDED.score,
                passed = EXCLUDED.passed,
                metrics = EXCLUDED.metrics,
                deductions = EXCLUDED.deductions,
                failed_validation_message = EXCLUDED.failed_validation_message,
                failed_validation_rules = EXCLUDED.failed_validation_rules,
                updated_at = NOW()
            RETURNING id, monitoring_file_run_id, monitoring_file_id, score, passed, metrics, deductions,
                      failed_validation_message, failed_validation_rules, created_at, updated_at
        """
        rows = self._db.execute_query(
            sql,
            [
                monitoring_file_run_id,
                monitoring_file_id,
                score,
                passed,
                json.dumps(metrics),
                json.dumps(deductions),
                failed_validation_message,
                json.dumps(failed_validation_rules) if failed_validation_rules else None,
            ],
        )
        row = rows[0]

        return MonitoringFileDataQuality(
            id=row["id"],
            monitoring_file_run_id=row["monitoring_file_run_id"],
            monitoring_file_id=row.get("monitoring_file_id"),
            score=row["score"],
            passed=row["passed"],
            metrics=row.get("metrics") or {},
            deductions=row.get("deductions") or {},
            failed_validation_message=row.get("failed_validation_message"),
            failed_validation_rules=row.get("failed_validation_rules"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    # -------------------------------------------------------------------------
    # MonitoringFileDataProfile operations
    # -------------------------------------------------------------------------

    def upsert_data_profile(
        self,
        monitoring_file_run_id: int,
        monitoring_file_id: Optional[int],
        profile_payload: Dict[str, Any],
    ) -> MonitoringFileDataProfile:
        """Upsert a data profile record for a run.

        Args:
            monitoring_file_run_id: The run ID.
            monitoring_file_id: Optional monitoring file ID.
            profile_payload: Profile JSON payload.

        Returns:
            The upserted MonitoringFileDataProfile.
        """
        import json

        sql = """
            INSERT INTO reporting.monitoring_file_data_profile
                (monitoring_file_run_id, monitoring_file_id, statistical_summary, completeness_overview,
                 type_format_issues, uniqueness_overview, value_distributions,
                 bounds_anomalies, sample_data, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (monitoring_file_run_id)
            DO UPDATE SET
                monitoring_file_id = EXCLUDED.monitoring_file_id,
                statistical_summary = EXCLUDED.statistical_summary,
                completeness_overview = EXCLUDED.completeness_overview,
                type_format_issues = EXCLUDED.type_format_issues,
                uniqueness_overview = EXCLUDED.uniqueness_overview,
                value_distributions = EXCLUDED.value_distributions,
                bounds_anomalies = EXCLUDED.bounds_anomalies,
                sample_data = EXCLUDED.sample_data,
                updated_at = NOW()
            RETURNING id, monitoring_file_run_id, monitoring_file_id, statistical_summary, completeness_overview,
                      type_format_issues, uniqueness_overview, value_distributions,
                      bounds_anomalies, sample_data, created_at, updated_at
        """
        # Support both snake_case and camelCase keys from different profiler outputs.
        # Map known logical sections into DB columns.
        key_map = {
            "statistical_summary": ["statistical_summary", "statisticalSummary"],
            "completeness_overview": ["completeness_overview", "completenessOverview"],
            "type_format_issues": ["type_format_issues", "typeFormatIssues"],
            "uniqueness_overview": ["uniqueness_overview", "uniquenessOverview"],
            "value_distributions": ["value_distributions", "valueDistributions"],
            "bounds_anomalies": ["bounds_anomalies", "boundsAnomalies"],
            "sample_data": ["sample_data", "sampleData"],
        }

        # Helper to fetch first matching key from payload
        def _get_first(payload: Dict[str, Any], candidates: List[str], default: Any):
            for k in candidates:
                if k in payload:
                    return payload.get(k)
            return default

        # Extract mapped sections; if none of the mapped keys are present,
        # fall back to storing the raw payload under sample_data.raw
        ss = _get_first(profile_payload, key_map["statistical_summary"], [])
        co = _get_first(profile_payload, key_map["completeness_overview"], [])
        tf = _get_first(profile_payload, key_map["type_format_issues"], [])
        uu = _get_first(profile_payload, key_map["uniqueness_overview"], [])
        vd = _get_first(profile_payload, key_map["value_distributions"], [])
        ba = _get_first(profile_payload, key_map["bounds_anomalies"], [])
        sd = _get_first(profile_payload, key_map["sample_data"], {})

        # Ensure sample_data is a dict and always preserve the raw payload
        if not isinstance(sd, dict):
            sd = {"raw": sd} if sd else {"raw": None}
        # Sanitize raw payload to a JSON-serializable structure to avoid circular refs
        try:
            # Use json.dumps with default=str to coerce non-serializable types, then load back
            safe_raw = json.loads(json.dumps(profile_payload, default=str))
            sd["raw"] = safe_raw
        except Exception:
            # Fallback: use string repr to guarantee serializability
            sd["raw"] = str(profile_payload)

        # Debug: log which sections we will persist (non-empty)
        try:
            present = {k: bool(v) for k, v in (
                ("statistical_summary", ss),
                ("completeness_overview", co),
                ("type_format_issues", tf),
                ("uniqueness_overview", uu),
                ("value_distributions", vd),
                ("bounds_anomalies", ba),
                ("sample_data", sd),
            )}
            logger.debug("Persisting profile sections for run %s: %s", monitoring_file_run_id, present)
        except Exception:
            logger.debug("Persisting profile sections for run %s (failed to introspect)", monitoring_file_run_id)

        rows = self._db.execute_query(
            sql,
            [
                monitoring_file_run_id,
                monitoring_file_id,
                json.dumps(ss),
                json.dumps(co),
                json.dumps(tf),
                json.dumps(uu),
                json.dumps(vd),
                json.dumps(ba),
                json.dumps(sd),
            ],
        )
        row = rows[0]

        return MonitoringFileDataProfile(
            id=row["id"],
            monitoring_file_run_id=row["monitoring_file_run_id"],
            monitoring_file_id=row.get("monitoring_file_id"),
            statistical_summary=row.get("statistical_summary") or [],
            completeness_overview=row.get("completeness_overview") or [],
            type_format_issues=row.get("type_format_issues") or [],
            uniqueness_overview=row.get("uniqueness_overview") or [],
            value_distributions=row.get("value_distributions") or [],
            bounds_anomalies=row.get("bounds_anomalies") or [],
            sample_data=row.get("sample_data") or {},
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
