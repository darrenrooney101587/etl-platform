"""Repository layer for data quality pipeline database operations.

This repository handles all database interactions for the data quality pipeline,
including monitoring file lookups, run creation/upserts, and quality result persistence.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from django import setup as django_setup
from django.apps import apps
from etl_database_schema.apps.bms_reporting.models import (
    MonitoringFile as ORMMonitoringFile,
    MonitoringFileRun as ORMMonitoringFileRun,
    MonitoringFileDataQuality as ORMMonitoringFileDataQuality,
    MonitoringFileDataProfile as ORMMonitoringFileDataProfile,
    MonitoringFileSchemaDefinition as ORMSchemaDefinition,
    MonitoringFileSchemaDefinitionVersion as ORMSchemaDefinitionVersion,
)

from etl_core.database.client import DatabaseClient
from pipeline_processing.models.monitoring import (
    MonitoringFile,
    MonitoringFileDataProfile,
    MonitoringFileDataQuality,
    MonitoringFileRun,
    MonitoringFileSchemaDefinition,
)

logger = logging.getLogger(__name__)


def _bootstrap_django_if_needed(settings_module: str = "file_processing.settings") -> None:
    """Ensure Django is configured before ORM access.

    Raises RuntimeError if settings are missing or bootstrap fails.
    """
    current = os.environ.get("DJANGO_SETTINGS_MODULE")
    if current and current != settings_module:
        raise RuntimeError(
            f"DJANGO_SETTINGS_MODULE already set to '{current}', expected '{settings_module}'"
        )
    if apps.ready:
        return
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)
    django_setup()


# --- ORM helpers ---------------------------------------------------------
def _import_monitoring_models() -> Tuple[
    type[ORMMonitoringFile],
    type[ORMMonitoringFileRun],
    type[ORMMonitoringFileDataQuality],
    type[ORMMonitoringFileDataProfile],
    type[ORMSchemaDefinition],
    type[ORMSchemaDefinitionVersion],
]:
    """Import upstream ORM models; requires Django to be bootstrapped."""
    _bootstrap_django_if_needed()
    return (
        ORMMonitoringFile,
        ORMMonitoringFileRun,
        ORMMonitoringFileDataQuality,
        ORMMonitoringFileDataProfile,
        ORMSchemaDefinition,
        ORMSchemaDefinitionVersion,
    )


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
        s3_key: Optional[str] = None,
    ) -> Optional[MonitoringFile]:
        """Look up a monitoring file by agency slug and file name.

        Prefer ORM lookup when possible; requires Django settings.
        """
        orm = _import_monitoring_models()
        (
            ORMMonitoringFile,
            ORMMonitoringFileRun,
            ORMMonitoringFileDataQuality,
            ORMMonitoringFileDataProfile,
            ORMSchemaDefinition,
            ORMSchemaDefinitionVersion,
        ) = orm

        try:
            # Resolve environment mapping same as SQL path
            environment = (os.getenv("ENVIRONMENT", "prod") or "prod").strip().lower()
            if environment in ("production", "prod", "prod-etl", "prod_etl", "production-etl"):
                environment = "prod"
            if environment not in ("prod", "qa", "sandbox"):
                environment = "prod"

            mapping_sql = f"SELECT {environment}_bms_slug, {environment}_bms_id FROM reporting.ref_agency_designations WHERE {environment}_s3_slug = %s"
            mapping_rows = self._db.execute_query(mapping_sql, [agency_slug]) if self._db else []

            internal_slug = agency_slug
            bms_id: Optional[int] = None
            if mapping_rows:
                mapped = mapping_rows[0]
                bms_slug = mapped.get(f"{environment}_bms_slug")
                mapped_bms_id = mapped.get(f"{environment}_bms_id")
                if bms_slug:
                    internal_slug = bms_slug
                if mapped_bms_id:
                    try:
                        bms_id = int(mapped_bms_id)
                    except Exception:
                        bms_id = None

            qs = ORMMonitoringFile.objects.all()
            if bms_id is not None:
                qs = qs.filter(agency_id=bms_id, file_name=file_name)
            else:
                qs = qs.filter(agency_slug__iexact=internal_slug, file_name=file_name)

            qs = qs.order_by("is_suppressed", "-id")
            results = list(qs)

            # Fallback to trying original s3 slug if none found
            if not results and bms_id is not None:
                qs2 = ORMMonitoringFile.objects.filter(agency_slug__iexact=agency_slug, file_name=file_name).order_by("is_suppressed", "-id")
                results = list(qs2)
            if not results and internal_slug != agency_slug:
                qs3 = ORMMonitoringFile.objects.filter(agency_slug__iexact=agency_slug, file_name=file_name).order_by("is_suppressed", "-id")
                results = list(qs3)

            if not results:
                # try filename-only fallback
                try:
                    fallback = ORMMonitoringFile.objects.filter(file_name=file_name).order_by("is_suppressed", "-id").first()
                    if fallback:
                        logger.warning(
                            "No monitoring_file for agency=%s (internal=%s) file=%s; falling back to file_name-only match id=%s agency=%s",
                            agency_slug,
                            internal_slug,
                            file_name,
                            fallback.id,
                            fallback.agency_slug,
                        )
                        return MonitoringFile(
                            id=fallback.id,
                            file_name=fallback.file_name,
                            agency_slug=fallback.agency_slug,
                            latest_data_quality_score=getattr(fallback, "latest_data_quality_score", None),
                            schema_definition_id=(getattr(fallback, "schema_definition_id", None) or (fallback.schema_definition.id if getattr(fallback, "schema_definition", None) else None)),
                            schema_definition_version_id=(getattr(fallback, "schema_definition_version_id", None) or (fallback.schema_definition_version.id if getattr(fallback, "schema_definition_version", None) else None)),
                            is_suppressed=getattr(fallback, "is_suppressed", False),
                        )
                except Exception:
                    logger.exception("Fallback ORM lookup by file_name failed")
                    return None
                return None

            # If multiple, apply s3_key disambiguation
            selected = results[0]
            if s3_key and len(results) > 1:
                search_suffix = s3_key.strip().lstrip("/")
                matches = [r for r in results if r.s3_url and (r.s3_url == search_suffix or r.s3_url.endswith("/" + search_suffix))]
                if matches:
                    selected = matches[0]

            return MonitoringFile(
                id=selected.id,
                file_name=selected.file_name,
                agency_slug=selected.agency_slug,
                latest_data_quality_score=getattr(selected, "latest_data_quality_score", None),
                schema_definition_id=(getattr(selected, "schema_definition_id", None) or (selected.schema_definition.id if getattr(selected, "schema_definition", None) else None)),
                schema_definition_version_id=(getattr(selected, "schema_definition_version_id", None) or (selected.schema_definition_version.id if getattr(selected, "schema_definition_version", None) else None)),
                is_suppressed=getattr(selected, "is_suppressed", False),
            )
        except Exception:
            # If ORM path errors, fall through to SQL fallback
            logger.exception("ORM path failed in get_monitoring_file; falling back to SQL")

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
                    mf.schema_definition_version_id,
                    mf.s3_url,
                    mf.is_suppressed
                FROM reporting.monitoring_file mf
                WHERE mf.agency_id = %s
                  AND mf.file_name = %s
                ORDER BY mf.is_suppressed ASC, mf.id DESC
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
                    mf.schema_definition_version_id,
                    mf.s3_url,
                    mf.is_suppressed
                FROM reporting.monitoring_file mf
                WHERE lower(mf.agency_slug) = lower(%s)
                  AND mf.file_name = %s
                ORDER BY mf.is_suppressed ASC, mf.id DESC
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
                        mf.schema_definition_version_id,
                        mf.s3_url,
                        mf.is_suppressed
                    FROM reporting.monitoring_file mf
                    WHERE lower(mf.agency_slug) = lower(%s)
                      AND mf.file_name = %s
                    ORDER BY mf.is_suppressed ASC, mf.id DESC
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
                        mf.schema_definition_version_id,
                        mf.s3_url,
                        mf.is_suppressed
                    FROM reporting.monitoring_file mf
                    WHERE mf.file_name = %s
                    ORDER BY mf.is_suppressed ASC, mf.id DESC
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
                        schema_definition_version_id=row.get("schema_definition_version_id"),
                        is_suppressed=row.get("is_suppressed", False),
                    )
            except Exception:
                logger.exception("Fallback lookup by file_name failed")
                return None

            return None

        # Determine the best matching row if multiple are found
        selected_row = rows[0]

        if s3_key and len(rows) > 1:
            # Filter rows where s3_url ends with the provided s3_key
            # The database s3_url might contain the bucket prefix or just the path.
            # We treat s3_key as the suffix we are looking for.
            search_suffix = s3_key.strip().lstrip("/")
            matches = []
            for r in rows:
                db_url = (r.get("s3_url") or "").strip()
                # Check for suffix match. Be careful of cases where db_url is empty.
                if db_url and (db_url == search_suffix or db_url.endswith("/" + search_suffix)):
                    matches.append(r)

            if matches:
                # If we found matches matching the key, use the first one (respecting sort order: not-suppressed first)
                selected_row = matches[0]
                if len(matches) > 1:
                    logger.debug(
                        "Found %d rows ending with s3_key='%s'; selected id=%s",
                        len(matches),
                        s3_key,
                        selected_row["id"]
                    )
            else:
                logger.debug(
                    "No rows matched s3_key='%s' suffix; falling back to top ranked row id=%s",
                    s3_key,
                    selected_row["id"]
                )

        row = selected_row
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
            schema_definition_version_id=row.get("schema_definition_version_id"),
            is_suppressed=row.get("is_suppressed", False),
        )

    def get_monitoring_file_by_id(self, monitoring_file_id: int) -> Optional[MonitoringFile]:
        """Look up a monitoring file by ID.

        Args:
            monitoring_file_id: The monitoring file ID.

        Returns:
            MonitoringFile if found, None otherwise.
        """
        # Try ORM first
        orm = _import_monitoring_models()
        if orm:
            ORMMonitoringFile = orm[0]
            try:
                obj = ORMMonitoringFile.objects.filter(id=monitoring_file_id).first()
                if not obj:
                    return None
                return MonitoringFile(
                    id=obj.id,
                    file_name=obj.file_name,
                    agency_slug=obj.agency_slug,
                    latest_data_quality_score=getattr(obj, "latest_data_quality_score", None),
                    schema_definition_id=(getattr(obj, "schema_definition_id", None) or (obj.schema_definition.id if getattr(obj, "schema_definition", None) else None)),
                    schema_definition_version_id=(getattr(obj, "schema_definition_version_id", None) or (obj.schema_definition_version.id if getattr(obj, "schema_definition_version", None) else None)),
                )
            except Exception:
                logger.exception("ORM get_monitoring_file_by_id failed; falling back to SQL")

        sql = """
            SELECT
                mf.id,
                mf.file_name,
                mf.agency_slug,
                mf.latest_data_quality_score,
                mf.schema_definition_id,
                mf.schema_definition_version_id
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
            schema_definition_version_id=row.get("schema_definition_version_id"),
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
        schema_definition_version_id: Optional[int] = None,
        s3_url: Optional[str] = None,
    ) -> MonitoringFile:
        """Create a new monitoring file record.

        Args:
            agency_slug: The agency slug identifier.
            file_name: The file name identifier.
            schema_definition_id: Optional schema definition FK.
            schema_definition_version_id: Optional schema version ID FK to pin specific version.
            s3_url: Optional S3 URL or path for the file (populates not-null s3_url column if required).

        Returns:
            The created MonitoringFile.
        """
        # Try ORM creation first
        orm = _import_monitoring_models()
        if orm:
            ORMMonitoringFile = orm[0]
            try:
                # Prepare kwargs for creation; fill simple defaults similar to SQL path
                kwargs: Dict[str, Any] = {
                    "s3_url": s3_url or "",
                    "agency_slug": agency_slug,
                    "file_name": file_name,
                }
                if schema_definition_id is not None:
                    kwargs["schema_definition_id"] = schema_definition_id
                if schema_definition_version_id is not None:
                    kwargs["schema_definition_version_id"] = schema_definition_version_id

                obj = ORMMonitoringFile.objects.create(**kwargs)
                return MonitoringFile(
                    id=obj.id,
                    file_name=obj.file_name,
                    agency_slug=obj.agency_slug,
                    latest_data_quality_score=getattr(obj, "latest_data_quality_score", None),
                    schema_definition_id=(getattr(obj, "schema_definition_id", None) or (obj.schema_definition.id if getattr(obj, "schema_definition", None) else None)),
                    schema_definition_version_id=(getattr(obj, "schema_definition_version_id", None) or (obj.schema_definition_version.id if getattr(obj, "schema_definition_version", None) else None)),
                    is_suppressed=getattr(obj, "is_suppressed", False),
                )
            except Exception:
                logger.exception("ORM create_monitoring_file failed; falling back to SQL")

        # base values we always want to set
        base_cols: Dict[str, Any] = {
            "s3_url": s3_url or "",
            "agency_slug": agency_slug,
            "file_name": file_name,
            "schema_definition_id": schema_definition_id,
            "schema_definition_version_id": schema_definition_version_id,
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

        # TODO: REVIEW AUTOMATIC CREATION
        # This method currently auto-creates a monitoring_file row when none exists.
        # When we migrate the full file monitoring service into this repository,
        # we should re-evaluate whether this repository should be responsible for
        # creating monitoring_file records. In production the monitoring_file
        # records are expected to be provisioned by an upstream system; auto-creating
        # here is a convenience for local/dev/test workflows but can mask missing
        # provisioning in production. Consider gating this behavior behind an
        # explicit "create_if_missing" flag or removing it entirely during migration.

        # Build parametrized insert dynamically
        cols = ", ".join(base_cols.keys())
        placeholders = ", ".join(["%s"] * len(base_cols))
        sql = f"""
            INSERT INTO reporting.monitoring_file ({cols})
            VALUES ({placeholders})
            RETURNING id, file_name, agency_slug, latest_data_quality_score, schema_definition_id, schema_definition_version_id
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
                "SELECT id, file_name, agency_slug, latest_data_quality_score, schema_definition_id, schema_definition_version_id "
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
            schema_definition_version_id=row.get("schema_definition_version_id"),
            is_suppressed=row.get("is_suppressed", False),
        )

    def update_monitoring_file_score(
        self,
        monitoring_file_id: int,
        score: int,
    ) -> None:
        orm = _import_monitoring_models()
        if orm:
            ORMMonitoringFile = orm[0]
            try:
                ORMMonitoringFile.objects.filter(id=monitoring_file_id).update(latest_data_quality_score=score)
                return
            except Exception:
                logger.exception("ORM update_monitoring_file_score failed; falling back to SQL")

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
        schema_definition_version_id: Optional[int] = None,
    ) -> Optional[MonitoringFileSchemaDefinition]:
        orm = _import_monitoring_models()
        if orm:
            _, _, _, _, ORMSchemaDefinition, ORMSchemaDefinitionVersion = orm
            try:
                if schema_definition_version_id is not None:
                    v = ORMSchemaDefinitionVersion.objects.filter(schema_definition_id=schema_definition_id, id=schema_definition_version_id).first()
                    if not v:
                        return None
                    return MonitoringFileSchemaDefinition(
                        id=v.id,
                        name=v.schema_definition.name if getattr(v, "schema_definition", None) else None,
                        description=getattr(v.schema_definition, "description", None) if getattr(v, "schema_definition", None) else None,
                        definition=v.definition,
                        created_at=v.created_at,
                        updated_at=v.updated_at,
                    )
                else:
                    # Try to fetch the latest version row which holds the JSON `definition`.
                    v = ORMSchemaDefinitionVersion.objects.filter(schema_definition_id=schema_definition_id).order_by("-version").first()
                    if v:
                        return MonitoringFileSchemaDefinition(
                            id=v.schema_definition.id if getattr(v, "schema_definition", None) else schema_definition_id,
                            name=v.schema_definition.name if getattr(v, "schema_definition", None) else None,
                            description=getattr(v.schema_definition, "description", None) if getattr(v, "schema_definition", None) else None,
                            definition=v.definition,
                            created_at=v.created_at,
                            updated_at=v.updated_at,
                        )
                    # Fall back to parent definition record without JSON if no versions exist
                    d = ORMSchemaDefinition.objects.filter(id=schema_definition_id).first()
                    if not d:
                        return None
                    return MonitoringFileSchemaDefinition(
                        id=d.id,
                        name=d.name,
                        description=d.description,
                        definition={},
                        created_at=d.created_at,
                        updated_at=d.updated_at,
                    )
            except Exception:
                logger.exception("ORM get_schema_definition failed; falling back to SQL")

        # Fallback SQL: query the *version* table for the JSON `definition` field.
        # If a specific version id is provided, fetch that version row. Otherwise
        # fetch the latest active version (ordered by version DESC) for the
        # requested schema_definition_id.
        if schema_definition_version_id is not None:
            sql = """
                SELECT v.id as version_id, d.id as def_id, d.name, d.description, v.definition, v.created_at, v.updated_at
                FROM reporting.monitoring_file_schema_definition_version v
                JOIN reporting.monitoring_file_schema_definition d
                  ON v.schema_definition_id = d.id
                WHERE v.schema_definition_id = %s AND v.id = %s
                LIMIT 1
            """
            rows = self._db.execute_query(sql, [schema_definition_id, schema_definition_version_id])
            if not rows:
                return None
            row = rows[0]
            return MonitoringFileSchemaDefinition(
                id=row.get("def_id") or schema_definition_id,
                name=row.get("name"),
                description=row.get("description"),
                definition=row.get("definition") or {},
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
        else:
            # pick the latest version for the definition_id
            sql = """
                SELECT v.id as version_id, d.id as def_id, d.name, d.description, v.definition, v.created_at, v.updated_at
                FROM reporting.monitoring_file_schema_definition_version v
                JOIN reporting.monitoring_file_schema_definition d
                  ON v.schema_definition_id = d.id
                WHERE v.schema_definition_id = %s
                ORDER BY v.version DESC
                LIMIT 1
            """
            rows = self._db.execute_query(sql, [schema_definition_id])
            if not rows:
                # As a last resort, return the parent definition record without JSON
                sql_parent = """
                    SELECT id, name, description, created_at, updated_at
                    FROM reporting.monitoring_file_schema_definition
                    WHERE id = %s
                """
                prow = self._db.execute_query(sql_parent, [schema_definition_id])
                if not prow:
                    return None
                p = prow[0]
                return MonitoringFileSchemaDefinition(
                    id=p.get("id"),
                    name=p.get("name"),
                    description=p.get("description"),
                    definition={},
                    created_at=p.get("created_at"),
                    updated_at=p.get("updated_at"),
                )
            row = rows[0]
            return MonitoringFileSchemaDefinition(
                id=row.get("def_id") or schema_definition_id,
                name=row.get("name"),
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
        # Try ORM transactional path first
        orm = _import_monitoring_models()
        if orm:
            ORMMonitoringFile, ORMMonitoringFileRun, _, _, _, _ = orm
            try:
                from django.db import transaction  # type: ignore

                with transaction.atomic():
                    # select existing run with a lock
                    existing = (
                        ORMMonitoringFileRun.objects.select_for_update()
                        .filter(monitoring_file_id=monitoring_file_id, run_date=run_date, run_hour=run_hour)
                        .first()
                    )
                    if existing:
                        # update metadata if provided
                        if file_last_modified is not None or file_size is not None:
                            update_fields = {}
                            if file_last_modified is not None:
                                update_fields["file_last_modified"] = file_last_modified
                            if file_size is not None:
                                update_fields["file_size"] = file_size
                            if update_fields:
                                ORMMonitoringFileRun.objects.filter(id=existing.id).update(**update_fields)
                                # refresh existing attributes
                                for k, v in update_fields.items():
                                    setattr(existing, k, v)
                        return MonitoringFileRun(
                            id=existing.id,
                            monitoring_file_id=existing.monitoring_file_id,
                            run_date=existing.run_date,
                            run_hour=existing.run_hour,
                            agency_id=getattr(existing, "agency_id", None),
                            created_at=existing.created_at,
                            updated_at=existing.updated_at,
                            file_last_modified=getattr(existing, "file_last_modified", None),
                            file_range_lower_limit=getattr(existing, "file_range_lower_limit", None),
                            file_size=getattr(existing, "file_size", None),
                        )
                    # Create new run
                    obj = ORMMonitoringFileRun.objects.create(
                        monitoring_file_id=monitoring_file_id,
                        run_date=run_date,
                        run_hour=run_hour,
                        agency_id=agency_id,
                        file_last_modified=file_last_modified,
                        file_size=file_size or 0,
                    )
                    return MonitoringFileRun(
                        id=obj.id,
                        monitoring_file_id=obj.monitoring_file_id,
                        run_date=obj.run_date,
                        run_hour=obj.run_hour,
                        agency_id=getattr(obj, "agency_id", None),
                        created_at=obj.created_at,
                        updated_at=obj.updated_at,
                        file_last_modified=getattr(obj, "file_last_modified", None),
                        file_range_lower_limit=getattr(obj, "file_range_lower_limit", None),
                        file_size=getattr(obj, "file_size", None),
                    )
            except Exception:
                logger.exception("ORM get_or_create_run failed; falling back to SQL")

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

        if file_size is None:
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
        orm = _import_monitoring_models()
        if orm:
            ORMMonitoringFileRun = orm[1]
            try:
                obj = ORMMonitoringFileRun.objects.filter(monitoring_file_id=monitoring_file_id, run_date=run_date, run_hour=run_hour).first()
                if not obj:
                    return None
                return MonitoringFileRun(
                    id=obj.id,
                    monitoring_file_id=obj.monitoring_file_id,
                    run_date=obj.run_date,
                    run_hour=obj.run_hour,
                    agency_id=getattr(obj, "agency_id", None),
                    created_at=obj.created_at,
                    updated_at=obj.updated_at,
                    file_last_modified=getattr(obj, "file_last_modified", None),
                    file_range_lower_limit=getattr(obj, "file_range_lower_limit", None),
                    file_size=getattr(obj, "file_size", None),
                )
            except Exception:
                logger.exception("ORM get_run failed; falling back to SQL")

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
        orm = _import_monitoring_models()
        if orm:
            ORMMonitoringFileRun = orm[1]
            try:
                obj = ORMMonitoringFileRun.objects.filter(monitoring_file_id=monitoring_file_id).order_by("-created_at").first()
                if not obj:
                    return None
                return MonitoringFileRun(
                    id=obj.id,
                    monitoring_file_id=obj.monitoring_file_id,
                    run_date=obj.run_date,
                    run_hour=obj.run_hour,
                    agency_id=getattr(obj, "agency_id", None),
                    created_at=obj.created_at,
                    updated_at=obj.updated_at,
                    file_last_modified=getattr(obj, "file_last_modified", None),
                    file_range_lower_limit=getattr(obj, "file_range_lower_limit", None),
                    file_size=getattr(obj, "file_size", None),
                )
            except Exception:
                logger.exception("ORM get_latest_run failed; falling back to SQL")

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
        orm = _import_monitoring_models()
        if orm:
            ORMMonitoringFileRun = orm[1]
            try:
                updates: Dict[str, Any] = {}
                if file_last_modified is not None:
                    updates["file_last_modified"] = file_last_modified
                if file_size is not None:
                    updates["file_size"] = file_size
                if updates:
                    ORMMonitoringFileRun.objects.filter(id=run_id).update(**updates)
                    return
            except Exception:
                logger.exception("ORM _update_run_metadata failed; falling back to SQL")

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
        orm = _import_monitoring_models()
        if orm:
            _, _, ORMMonitoringFileDataQuality, _, _, _ = orm
            try:
                # ORM update_or_create
                defaults = {
                    "monitoring_file_id": monitoring_file_id,
                    "score": score,
                    "passed": passed,
                    "metrics": metrics,
                    "deductions": deductions,
                    "failed_validation_message": failed_validation_message,
                    "failed_validation_rules": failed_validation_rules,
                }
                obj, created = ORMMonitoringFileDataQuality.objects.update_or_create(
                    monitoring_file_run_id=monitoring_file_run_id, defaults=defaults
                )
                return MonitoringFileDataQuality(
                    id=obj.id,
                    monitoring_file_run_id=obj.monitoring_file_run_id,
                    monitoring_file_id=getattr(obj, "monitoring_file_id", None),
                    score=obj.score,
                    passed=obj.passed,
                    metrics=getattr(obj, "metrics", {}) or {},
                    deductions=getattr(obj, "deductions", {}) or {},
                    failed_validation_message=getattr(obj, "failed_validation_message", None),
                    failed_validation_rules=getattr(obj, "failed_validation_rules", None),
                    created_at=obj.created_at,
                    updated_at=obj.updated_at,
                )
            except Exception:
                logger.exception("ORM upsert_data_quality failed; falling back to SQL")

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
        orm = _import_monitoring_models()
        if orm:
            _, _, _, ORMMonitoringFileDataProfile, _, _ = orm
            try:
                # Map payload sections same as SQL path
                key_map = {
                    "statistical_summary": ["statistical_summary", "statisticalSummary"],
                    "completeness_overview": ["completeness_overview", "completenessOverview"],
                    "type_format_issues": ["type_format_issues", "typeFormatIssues"],
                    "uniqueness_overview": ["uniqueness_overview", "uniquenessOverview"],
                    "value_distributions": ["value_distributions", "valueDistributions"],
                    "bounds_anomalies": ["bounds_anomalies", "boundsAnomalies"],
                    "sample_data": ["sample_data", "sampleData"],
                }

                def _get_first(payload, candidates, default):
                    for k in candidates:
                        if k in payload:
                            return payload.get(k)
                    return default

                ss = _get_first(profile_payload, key_map["statistical_summary"], [])
                co = _get_first(profile_payload, key_map["completeness_overview"], [])
                tf = _get_first(profile_payload, key_map["type_format_issues"], [])
                uu = _get_first(profile_payload, key_map["uniqueness_overview"], [])
                vd = _get_first(profile_payload, key_map["value_distributions"], [])
                ba = _get_first(profile_payload, key_map["bounds_anomalies"], [])
                sd = _get_first(profile_payload, key_map["sample_data"], {})

                if not isinstance(sd, dict):
                    sd = {"raw": sd} if sd else {"raw": None}

                defaults = {
                    "monitoring_file_id": monitoring_file_id,
                    "statistical_summary": ss,
                    "completeness_overview": co,
                    "type_format_issues": tf,
                    "uniqueness_overview": uu,
                    "value_distributions": vd,
                    "bounds_anomalies": ba,
                    "sample_data": sd,
                }
                obj, created = ORMMonitoringFileDataProfile.objects.update_or_create(
                    monitoring_file_run_id=monitoring_file_run_id, defaults=defaults
                )
                return MonitoringFileDataProfile(
                    id=obj.id,
                    monitoring_file_run_id=obj.monitoring_file_run_id,
                    monitoring_file_id=getattr(obj, "monitoring_file_id", None),
                    statistical_summary=getattr(obj, "statistical_summary", []) or [],
                    completeness_overview=getattr(obj, "completeness_overview", []) or [],
                    type_format_issues=getattr(obj, "type_format_issues", []) or [],
                    uniqueness_overview=getattr(obj, "uniqueness_overview", []) or [],
                    value_distributions=getattr(obj, "value_distributions", []) or [],
                    bounds_anomalies=getattr(obj, "bounds_anomalies", []) or [],
                    sample_data=getattr(obj, "sample_data", {}) or {},
                    created_at=obj.created_at,
                    updated_at=obj.updated_at,
                )
            except Exception:
                logger.exception("ORM upsert_data_profile failed; falling back to SQL")

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
