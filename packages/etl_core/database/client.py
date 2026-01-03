import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DatabaseClient:
    """Lightweight psycopg2-backed DB client for executing queries.

    Responsibilities:
    - Provide a minimal, DI-friendly API for executing SQL and returning dict rows.
    - Avoid embedding domain-specific SQL. Domain repositories should live in package modules
      (for example `packages/data_pipeline/repositories`).

    Construction:
      - Pass an existing DB connection via `connection` for tests, or
      - Provide a DSN via `dsn`, or rely on environment variables (DATABASE_URL or DB_*).
    """

    def __init__(self, connection: Optional[Any] = None, dsn: Optional[str] = None, connections: Optional[Any] = None, db_alias: str = "bms") -> None:
        self._conn: Optional[Any] = connection
        self._dsn = dsn
        self._connections = connections
        self._db_alias = db_alias

    def _ensure_connection(self) -> Any:
        """Lazily create and return a psycopg2 connection.

        The psycopg2 import is deferred until a real connection is required so the
        module can be imported in environments where the driver is not installed.
        """
        if self._conn:
            return self._conn

        try:
            import psycopg2
            from psycopg2 import extras  # noqa: F401 - imported for cursor factories
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError(
                "psycopg2 is required to use DatabaseClient. Install 'psycopg2-binary'."
            ) from exc

        if self._dsn:
            conn = psycopg2.connect(self._dsn)
        else:
            dsn_env = os.getenv("DATABASE_URL")
            if dsn_env:
                conn = psycopg2.connect(dsn_env)
            else:
                host = os.getenv("DB_HOST", "localhost")
                port = int(os.getenv("DB_PORT", "5432"))
                dbname = os.getenv("DB_NAME", "postgres")
                user = os.getenv("DB_USER", "postgres")
                password = os.getenv("DB_PASSWORD", "")
                sslmode = os.getenv("DB_SSLMODE", "prefer")

                conn = psycopg2.connect(
                    host=host,
                    port=port,
                    dbname=dbname,
                    user=user,
                    password=password,
                    sslmode=sslmode,
                )

        # Use autocommit for simple read queries
        conn.autocommit = True
        self._conn = conn
        return self._conn

    def close(self) -> None:
        """Close the underlying DB connection, if any."""
        try:
            if self._conn:
                self._conn.close()
        finally:
            self._conn = None

    def _log_db_connections(self, context: str) -> None:
        """Log configured DB settings for debugging without exposing secrets."""
        try:
            dsn = self._dsn or os.getenv("DATABASE_URL")
            if dsn:
                logger.info(f"{context} -> using DSN connection (redacted)")
                return
            host = os.getenv("DB_HOST", "localhost")
            port = os.getenv("DB_PORT", "5432")
            dbname = os.getenv("DB_NAME", "<unset>")
            user = os.getenv("DB_USER", "<unset>")
            logger.info(f"{context} -> host={host} port={port} db={dbname} user={user}")
        except Exception as exc:
            logger.warning(f"{context} -> failed to log DB settings: {exc}")

    def execute_query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute a read-only SQL query and return rows as dictionaries.

        This is the only query surface etl_core exposes; domain SQL must live in
        package-level repositories (for example, `packages/data_pipeline/repositories`).

        Args:
            sql: SQL statement to execute.
            params: Optional list/tuple of parameters.

        Returns:
            List of rows as dicts.
        """
        self._log_db_connections("execute_query")
        try:
            conn = self._ensure_connection()
            import psycopg2.extras as _extras  # type: ignore
            with conn.cursor(cursor_factory=_extras.RealDictCursor) as cursor:
                cursor.execute(sql, params or [])
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("Database query failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Backwards-compatible domain methods (tests expect these on the client)
    # These methods use a provided `connections` mapping (Django style) when
    # available (the test harness injects a MagicMock for this). Otherwise
    # they fall back to the generic execute_query surface.
    # ------------------------------------------------------------------
    def _execute_via_connections(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        if not self._connections:
            return self.execute_query(sql, params)

        with self._connections[self._db_alias].cursor() as cursor:
            cursor.execute(sql, params or [])
            columns = [col[0] for col in cursor.description] if cursor.description else []
            results: List[Dict[str, Any]] = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            return results

    def get_attachment_files_for_s3_processing(self, agency_id: int) -> List[Dict[str, Any]]:
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
                row_number() OVER (PARTITION BY a.original_filename, a.benchmark_user_id ORDER BY a.created DESC) AS rank
            FROM public.attachment a
            WHERE a.attachable_type IN ('UserDocument','Form')
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
            WHERE r.RANK = 1
        ), forms AS (
            SELECT
                bf.filename,
                bf.original_filename,
                bf.attachable_type,
                bf.mime_type,
                bf.byte_size,
                bf.benchmark_user_id,
                f.number AS relation_id,
                f.number || '_' || bf.filename AS output_filename
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
                bu.employee_id || '_' || bu.full_name || '_' || bf.original_filename AS output_filename
            FROM base_files bf
            JOIN public.benchmark_user bu
            ON bf.attachable_id = bu.id
            WHERE bf.attachable_type = 'UserDocument'
        )
        SELECT * FROM forms
        UNION
        SELECT * FROM users
        """
        return self._execute_via_connections(sql_query, [agency_id])

    def get_agency_s3_slug(self, agency_id: int) -> str:
        try:
            from etl_core.support.utilities import get_env_bms_id_field, get_env_s3_field
        except Exception:
            from etl_core.support.utilities import get_env_bms_id_field, get_env_s3_field

        where_clause = get_env_bms_id_field()
        select_column = get_env_s3_field()
        sql_query = f"""
                    SELECT {select_column}
                    FROM reporting.ref_agency_designations rad
                    WHERE {where_clause} = %s
                    """
        # If a Django-style connections mapping is provided, use cursor.fetchone()
        if self._connections:
            with self._connections[self._db_alias].cursor() as cursor:
                cursor.execute(sql_query, [int(agency_id)])
                result = cursor.fetchone()
                if result:
                    # result may be a tuple; return first element
                    return result[0] if isinstance(result, (list, tuple)) else result
                return ""

        # Fallback to generic execute_query which returns list of dict rows
        rows = self.execute_query(sql_query, [int(agency_id)])
        if rows:
            first = rows[0]
            # try to return select_column if present, otherwise first value
            return first.get(select_column) or (list(first.values())[0] if first else "")
        return ""

    def get_organization_employment_history(self, agency_id: int) -> List[Dict[str, Any]]:
        sql_query = """
        SELECT 
            ou.display_name,
            bu.employee_id,
            ueh.effective_date,
            ueh.employment_action,
            ueh.title_rank,
            ueh.employment_type,
            ueh.comment,
            ueh.status,
            ueh.supervisor,
            ueh.tour_of_duty,
            ueh.role
        FROM organization.tenant t 
        JOIN organization.organizational_unit ou 
        ON ou.tenant_id = t.id
        JOIN organization.user_organizational_unit_history uouh 
        ON ou.id = uouh.organizational_unit_id 
        JOIN organization.user_employment_history ueh 
        ON ueh.user_organizational_unit_history_id = uouh.id
        JOIN public.benchmark_user bu 
        ON bu.integration_id = uouh.user_id 
        WHERE t.agency_id = %s
        """
        return self._execute_via_connections(sql_query, [agency_id])


if __name__ == "__main__":
    # Minimal manual check when running directly (no DB calls executed)
    c = DatabaseClient()
    logger.info(f"DatabaseClient initialized: {bool(c)}")
