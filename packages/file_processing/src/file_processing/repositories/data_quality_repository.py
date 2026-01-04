"""Repository layer for data quality checks."""
from __future__ import annotations

from typing import Any, Dict, List

from etl_core.database.client import DatabaseClient


class DataQualityRepository:
    """Repository for attachment-related data quality queries."""

    def __init__(self, db: DatabaseClient) -> None:
        self._db = db

    def get_attachment_files_for_s3_processing(self, agency_id: int) -> List[Dict[str, Any]]:
        """Return latest unprocessed attachment files for the given agency."""
        sql_query = """
            WITH ranked AS (
                SELECT
                    a.filename,
                    a.original_filename,
                    a.mime_type,
                    CAST(a.benchmark_user_id AS integer) AS benchmark_user_id,
                    a.attachable_id,
                    a.attachable_type,
                    a.byte_size,
                    a.created,
                    row_number() OVER (
                        PARTITION BY a.original_filename, a.benchmark_user_id
                        ORDER BY a.created DESC
                    ) AS rank
                FROM public.attachment a
                WHERE a.attachable_type IN ('UserDocument', 'Form')
                  AND a.deleted = FALSE
                  AND a.processed = FALSE
            ), base_files AS (
                SELECT
                    r.filename,
                    r.original_filename,
                    r.attachable_type,
                    r.mime_type,
                    r.benchmark_user_id,
                    r.attachable_id,
                    r.byte_size
                FROM ranked r
                JOIN public.benchmark_user bu
                  ON bu.id = r.benchmark_user_id
                 AND bu.agency_id = %s
                WHERE r.rank = 1
            ), forms AS (
                SELECT
                    bf.filename,
                    bf.original_filename,
                    bf.attachable_type,
                    bf.mime_type,
                    bf.byte_size,
                    bf.benchmark_user_id,
                    f.number AS relation_id,
                    COALESCE(CAST(f.number AS text), '') || '_' || COALESCE(bf.filename, '') AS output_filename
                FROM base_files bf
                JOIN public.form f
                  ON bf.attachable_id = f.id
                WHERE bf.attachable_type = 'Form'
            ), users AS (
                SELECT
                    bf.filename,
                    bf.original_filename,
                    bf.attachable_type,
                    bf.mime_type,
                    bf.byte_size,
                    bf.benchmark_user_id,
                    bu.employee_id AS relation_id,
                    COALESCE(CAST(bu.employee_id AS text), '') || '_' || COALESCE(bu.full_name, '') || '_' || COALESCE(bf.original_filename, '') AS output_filename
                FROM base_files bf
                JOIN public.benchmark_user bu
                  ON bf.attachable_id = bu.id
                WHERE bf.attachable_type = 'UserDocument'
            )
            SELECT * FROM forms
            UNION
            SELECT * FROM users
        """
        return self._db.execute_query(sql_query, (agency_id,))
