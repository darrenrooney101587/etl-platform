import logging
from typing import Any, Dict, List, Optional

from django.db import connections as django_connections, connections
from data_pipeline.support.utilities import get_env_bms_id_field, get_env_s3_field

logger = logging.getLogger(__name__)


class DatabaseClient:
    """Database client for read-only reporting queries.

    Encapsulates database access to the BMS data source with dependency injection
    for testability. Environment-specific behavior (e.g., which columns to select)
    is provided via utilities.

    :param connections: Django connections mapping to use; defaults to django.db.connections
    :type connections: Optional[Any]
    :param db_alias: Database alias to use for queries; defaults to 'bms'
    :type db_alias: str
    """

    def __init__(self, db_alias: str = "bms") -> None:
        self._db_alias = db_alias

    def _log_db_connections(self, context: str, db_alias: str = "bms") -> None:
        """Log configured DB settings for debugging.

        :param context: Calling context for log correlation
        :type context: str
        """
        try:
            db_settings = connections[db_alias].settings_dict
            db_info = {
                self._db_alias: {
                    "USER": db_settings.get("USER"),
                    "NAME": db_settings.get("NAME"),
                    "HOST": db_settings.get("HOST"),
                    "PORT": db_settings.get("PORT"),
                }
            }
            print(f"{context} -> db_settings={db_info}")
        except Exception as exc:
            logger.warning(f"{context} -> failed to read DB settings: {exc}")

    def get_attachment_files_for_s3_processing(self, agency_id: int) -> List[Dict[str, Any]]:
        """Return latest unprocessed attachment files for the given agency.

        :param agency_id: Agency identifier
        :type agency_id: int
        :return: File mappings for S3 processing
        :rtype: List[Dict[str, Any]]
        :raises Exception: Propagates DB errors
        """
        self._log_db_connections("get_attachment_files_for_s3_processing", self._db_alias)

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

        try:
            with connections["bms"].cursor() as cursor:
                cursor.execute(sql_query, [agency_id])
                columns = [col[0] for col in cursor.description]
                results: List[Dict[str, Any]] = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                logger.info(f"Retrieved {len(results)} files for S3 processing from agency {agency_id}")
                return results
        except Exception as e:
            logger.error(f"Error executing S3 files query: {e}")
            raise

    def get_agency_s3_slug(self, agency_id: int) -> str:
        """Return the S3 slug for the given agency based on environment mapping.

        :param agency_id: Agency identifier
        :type agency_id: int
        :return: S3 slug or empty string when not found
        :rtype: str
        :raises Exception: Propagates DB errors
        """
        self._log_db_connections("get_agency_s3_slug")
        where_clause = get_env_bms_id_field()
        select_column = get_env_s3_field()

        sql_query = f"""
                    SELECT {select_column}
                    FROM reporting.ref_agency_designations rad
                    WHERE {where_clause} = %s
                    """
        try:
            with connections[self._db_alias].cursor() as cursor:
                cursor.execute(sql_query, [int(agency_id)])
                result = cursor.fetchone()
                if result:
                    print(result[0])
                    return result[0]
                logger.warning(f"No S3 slug found for agency ID {agency_id}")
                return ""
        except Exception as e:
            logger.error(f"Error retrieving S3 slug for agency ID {agency_id}: {e}")
            raise

    def get_organization_employment_history(self, agency_id: int) -> List[Dict[str, Any]]:
        """Return employment history records for all users in the given agency.

        :param agency_id: Agency identifier
        :type agency_id: int
        :return: Employment history rows
        :rtype: List[Dict[str, Any]]
        :raises Exception: Propagates DB errors
        """
        self._log_db_connections("get_organization_employment_history")
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

        try:
            with connections[self._db_alias].cursor() as cursor:
                cursor.execute(sql_query, [agency_id])
                columns = [col[0] for col in cursor.description]
                results: List[Dict[str, Any]] = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                logger.info(f"Retrieved {len(results)} employment history records for agency {agency_id}")
                return results
        except Exception as e:
            logger.error(f"Error executing employment history query: {e}")
            raise


if __name__ == "__main__":
    # Minimal manual check when running directly (no DB calls executed)
    client = DatabaseClient()
    logger.info(f"DatabaseClient initialized with alias 'bms': {bool(client)}")
