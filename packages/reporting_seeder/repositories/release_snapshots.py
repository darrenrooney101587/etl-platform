"""Repository utilities for reporting seeder release snapshots."""
from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from etl_core.database.client import DatabaseClient

ColumnDefinition = Dict[str, str]
ColumnStat = Dict[str, Any]
TopValueStat = Dict[str, Any]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ReleaseSnapshotRepository:
    """Repository for persisting and querying release snapshot metadata."""

    def __init__(
        self, db_client: DatabaseClient, snapshot_model: Optional[type] = None
    ) -> None:
        self._db = db_client
        self._snapshot_model = snapshot_model

    def _ensure_model(self) -> type:
        """Return the Django model used for release snapshots.

        :returns: Django ORM model class for release snapshots.
        :rtype: type
        :raises RuntimeError: When Django or the model import is unavailable.
        """
        if self._snapshot_model is not None:
            return self._snapshot_model
        try:
            from etl_core.models.apps.bms_reporting.models import SeederReleaseSnapshot

            return SeederReleaseSnapshot
        except Exception as exc:  # pragma: no cover - runtime dependency
            try:
                from reporting_seeder.models import SeederReleaseSnapshot

                return SeederReleaseSnapshot
            except Exception as fallback_exc:  # pragma: no cover - runtime dependency
                raise RuntimeError(
                    "Release snapshot models are not available. Ensure DJANGO_SETTINGS_MODULE is set "
                    "and reporting_seeder.django_bootstrap.bootstrap_django(...) has been called before using ReleaseSnapshotRepository."
                ) from fallback_exc

    def create_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a release snapshot via the ORM.

        :param snapshot: Snapshot payload to persist.
        :type snapshot: Dict[str, Any]
        :returns: Snapshot payload with ORM-generated identifiers.
        :rtype: Dict[str, Any]
        """
        model = self._ensure_model()
        instance = model.objects.create(**snapshot)
        snapshot["id"] = str(instance.id)
        return snapshot

    def get_snapshot_by_id(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single snapshot by id.

        :param snapshot_id: Snapshot UUID as a string.
        :type snapshot_id: str
        :returns: Snapshot row as a dict or None.
        :rtype: Optional[Dict[str, Any]]
        """
        model = self._ensure_model()
        rows = list(model.objects.filter(id=snapshot_id).values())
        return rows[0] if rows else None

    def list_snapshots_by_table(self, table_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """List snapshots for a table in newest-first order.

        :param table_name: Fully qualified table name.
        :type table_name: str
        :param limit: Maximum number of snapshots to return.
        :type limit: int
        :returns: Snapshot list ordered by release timestamp.
        :rtype: List[Dict[str, Any]]
        """
        model = self._ensure_model()
        return list(model.objects.filter(table_name=table_name).order_by("-released_at").values()[:limit])

    def list_snapshots_by_manifest(self, manifest_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """List snapshots for a manifest in newest-first order.

        :param manifest_id: Manifest primary key.
        :type manifest_id: int
        :param limit: Maximum number of snapshots to return.
        :type limit: int
        :returns: Snapshot list ordered by release timestamp.
        :rtype: List[Dict[str, Any]]
        """
        model = self._ensure_model()
        return list(model.objects.filter(manifest_id=manifest_id).order_by("-released_at").values()[:limit])

    def get_columns(self, table_name: str) -> List[ColumnDefinition]:
        """Return ordered column definitions for a table.

        :param table_name: Fully qualified table name.
        :type table_name: str
        :returns: Ordered list of column definitions (name/type pairs).
        :rtype: List[ColumnDefinition]
        """
        schema, name = _split_table_name(table_name)
        sql = """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """
        rows = self._db.execute_query(sql, [schema, name])
        columns: List[ColumnDefinition] = []
        for row in rows:
            columns.append(
                {
                    "name": str(row.get("column_name", "")),
                    "type": str(row.get("data_type", "")),
                }
            )
        return columns

    def get_total_rows(self, table_name: str) -> int:
        """Return total row count for a table.

        :param table_name: Fully qualified table name.
        :type table_name: str
        :returns: Row count.
        :rtype: int
        """
        sql_module = _get_sql_module()
        table_identifier = _get_table_identifier(table_name, sql_module)
        query = sql_module.SQL("SELECT COUNT(*) AS total_rows FROM {}").format(table_identifier)
        rows = self._db.execute_query(query)
        if not rows:
            return 0
        return int(rows[0].get("total_rows") or 0)

    def get_column_stats(
        self,
        table_name: str,
        columns: Sequence[ColumnDefinition],
        total_rows: int,
        top_values_columns: Optional[Iterable[str]] = None,
    ) -> List[ColumnStat]:
        """Compute per-column stats for a materialized view.

        :param table_name: Fully qualified table name.
        :type table_name: str
        :param columns: Ordered column definitions.
        :type columns: Sequence[ColumnDefinition]
        :param total_rows: Total row count for the table.
        :type total_rows: int
        :param top_values_columns: Optional column allowlist for top-value stats.
        :type top_values_columns: Optional[Iterable[str]]
        :returns: List of per-column stats.
        :rtype: List[ColumnStat]
        """
        sql_module = _get_sql_module()
        table_identifier = _get_table_identifier(table_name, sql_module)
        allowlist = {col.strip() for col in (top_values_columns or []) if col and col.strip()}
        stats: List[ColumnStat] = []
        for column in columns:
            column_name = column["name"]
            column_type = column["type"]
            column_identifier = _get_column_identifier(column_name, sql_module)
            include_min_max = _is_numeric_type(column_type) or _is_date_type(column_type)
            include_avg = _is_numeric_type(column_type)
            select_parts = [
                sql_module.SQL("COUNT(*) FILTER (WHERE {} IS NULL) AS null_count").format(column_identifier),
                sql_module.SQL("COUNT(DISTINCT {}) AS distinct_count").format(column_identifier),
            ]
            if include_min_max:
                select_parts.append(sql_module.SQL("MIN({}) AS min_value").format(column_identifier))
                select_parts.append(sql_module.SQL("MAX({}) AS max_value").format(column_identifier))
            if include_avg:
                select_parts.append(sql_module.SQL("AVG({}) AS avg_value").format(column_identifier))
            query = sql_module.SQL("SELECT {fields} FROM {table}").format(
                fields=sql_module.SQL(", ").join(select_parts),
                table=table_identifier,
            )
            summary_rows = self._db.execute_query(query)
            summary = summary_rows[0] if summary_rows else {}
            null_count = int(summary.get("null_count") or 0)
            distinct_count = int(summary.get("distinct_count") or 0)
            null_pct = (null_count / total_rows * 100.0) if total_rows else 0.0
            column_stat: ColumnStat = {
                "name": column_name,
                "type": column_type,
                "null_count": null_count,
                "null_pct": round(null_pct, 6),
                "distinct_count": distinct_count,
            }
            if include_min_max:
                column_stat["min"] = _coerce_json_value(summary.get("min_value"))
                column_stat["max"] = _coerce_json_value(summary.get("max_value"))
            if include_avg:
                column_stat["avg"] = _coerce_json_value(summary.get("avg_value"))
            if _should_collect_top_values(column_name, column_type, distinct_count, allowlist):
                column_stat["top_values"] = self._get_top_values(
                    table_identifier, column_identifier, total_rows
                )
            stats.append(column_stat)
        return stats

    def _get_top_values(
        self, table_identifier: Any, column_identifier: Any, total_rows: int, limit: int = 5
    ) -> List[TopValueStat]:
        """Fetch top value distribution for a column.

        :param table_identifier: psycopg2 SQL identifier for the table.
        :type table_identifier: Any
        :param column_identifier: psycopg2 SQL identifier for the column.
        :type column_identifier: Any
        :param total_rows: Total row count for denominator.
        :type total_rows: int
        :param limit: Max number of values to return.
        :type limit: int
        :returns: List of top values with counts and percentages.
        :rtype: List[TopValueStat]
        """
        sql_module = _get_sql_module()
        query = sql_module.SQL(
            "SELECT {column} AS value, COUNT(*) AS value_count "
            "FROM {table} "
            "WHERE {column} IS NOT NULL "
            "GROUP BY {column} "
            "ORDER BY value_count DESC "
            "LIMIT %s"
        ).format(column=column_identifier, table=table_identifier)
        rows = self._db.execute_query(query, [limit])
        top_values: List[TopValueStat] = []
        for row in rows:
            count = int(row.get("value_count") or 0)
            pct = (count / total_rows * 100.0) if total_rows else 0.0
            top_values.append(
                {
                    "value": _coerce_json_value(row.get("value")),
                    "count": count,
                    "pct": round(pct, 6),
                }
            )
        return top_values


def _split_table_name(table_name: str) -> Tuple[str, str]:
    """Split a table name into schema and relation parts.

    :param table_name: Fully qualified or unqualified table name.
    :type table_name: str
    :returns: Schema name and table name.
    :rtype: Tuple[str, str]
    :raises ValueError: When the name contains too many parts.
    """
    parts = [part for part in table_name.split(".") if part]
    if len(parts) == 1:
        _validate_identifier(parts[0])
        return "public", parts[0]
    if len(parts) == 2:
        _validate_identifier(parts[0])
        _validate_identifier(parts[1])
        return parts[0], parts[1]
    raise ValueError(f"Invalid table name: {table_name}")


def _get_sql_module() -> Any:
    """Return psycopg2.sql module for safe SQL composition.

    :returns: psycopg2.sql module.
    :rtype: Any
    :raises RuntimeError: When psycopg2 is unavailable.
    """
    try:
        from psycopg2 import sql
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("psycopg2 is required for snapshot SQL composition") from exc
    return sql


def _get_table_identifier(table_name: str, sql_module: Any) -> Any:
    """Create a qualified table identifier.

    :param table_name: Fully qualified or unqualified table name.
    :type table_name: str
    :param sql_module: psycopg2.sql module.
    :type sql_module: Any
    :returns: psycopg2 SQL identifier for the table.
    :rtype: Any
    """
    schema, name = _split_table_name(table_name)
    return sql_module.Identifier(schema, name)


def _get_column_identifier(column_name: str, sql_module: Any) -> Any:
    """Create a column identifier for SQL composition.

    :param column_name: Column name.
    :type column_name: str
    :param sql_module: psycopg2.sql module.
    :type sql_module: Any
    :returns: psycopg2 SQL identifier for the column.
    :rtype: Any
    """
    _validate_identifier(column_name)
    return sql_module.Identifier(column_name)


def _is_numeric_type(column_type: str) -> bool:
    """Return True when the column type is numeric.

    :param column_type: PostgreSQL column type string.
    :type column_type: str
    :returns: True for numeric types.
    :rtype: bool
    """
    normalized = column_type.lower()
    numeric_markers = (
        "smallint",
        "integer",
        "bigint",
        "decimal",
        "numeric",
        "real",
        "double precision",
        "float",
    )
    return any(marker in normalized for marker in numeric_markers)


def _is_date_type(column_type: str) -> bool:
    """Return True when the column type is date or timestamp-like.

    :param column_type: PostgreSQL column type string.
    :type column_type: str
    :returns: True for date-like types.
    :rtype: bool
    """
    normalized = column_type.lower()
    return "date" in normalized or "timestamp" in normalized or "time" in normalized


def _is_text_type(column_type: str) -> bool:
    """Return True for text/categorical column types.

    :param column_type: PostgreSQL column type string.
    :type column_type: str
    :returns: True if the type is considered text-like.
    :rtype: bool
    """
    normalized = column_type.lower()
    text_markers = ("character", "text", "varchar", "char")
    return any(marker in normalized for marker in text_markers)


def _should_collect_top_values(
    column_name: str,
    column_type: str,
    distinct_count: int,
    allowlist: Iterable[str],
    max_distinct: int = 50,
) -> bool:
    """Return True when top values should be computed for a column.

    :param column_name: Column name.
    :type column_name: str
    :param column_type: Column type string.
    :type column_type: str
    :param distinct_count: Distinct count observed in the column.
    :type distinct_count: int
    :param allowlist: Column allowlist for top values.
    :type allowlist: Iterable[str]
    :param max_distinct: Max distinct values for auto top-values.
    :type max_distinct: int
    :returns: True when top values should be collected.
    :rtype: bool
    """
    if column_name in allowlist:
        return True
    if not _is_text_type(column_type):
        return False
    return distinct_count <= max_distinct


def _validate_identifier(identifier: str) -> None:
    """Validate that an identifier is composed of safe characters.

    :param identifier: Identifier to validate.
    :type identifier: str
    :raises ValueError: When the identifier contains unsupported characters.
    """
    if not _IDENTIFIER_RE.match(identifier):
        raise ValueError(f"Unsafe identifier: {identifier}")


def _coerce_json_value(value: Any) -> Any:
    """Convert non-JSON-serializable values into JSON-friendly forms.

    :param value: Raw database value.
    :type value: Any
    :returns: JSON-friendly value.
    :rtype: Any
    """
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value
