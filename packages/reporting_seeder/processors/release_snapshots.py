"""Processor helpers for reporting seeder release snapshots and drift."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from reporting_seeder.repositories.release_snapshots import (
    ColumnDefinition,
    ColumnStat,
    ReleaseSnapshotRepository,
)

ZERO_BASE_DELTA_PCT = 100.0


class ReleaseSnapshotProcessor:
    """Capture release snapshots for materialized views."""

    def __init__(self, snapshot_repository: ReleaseSnapshotRepository) -> None:
        self._snapshots = snapshot_repository

    def capture_snapshot(
        self,
        manifest: Mapping[str, object],
        release_tag: str,
        release_version: Optional[str] = None,
        top_values_columns: Optional[Iterable[str]] = None,
        released_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Capture and persist a release snapshot for a manifest.

        :param manifest: Manifest row containing table/report metadata.
        :type manifest: Mapping[str, object]
        :param release_tag: Release tag or git SHA.
        :type release_tag: str
        :param release_version: Optional human-readable release version.
        :type release_version: Optional[str]
        :param top_values_columns: Optional column allowlist for top-value stats.
        :type top_values_columns: Optional[Iterable[str]]
        :param released_at: Optional release timestamp (defaults to now UTC).
        :type released_at: Optional[datetime]
        :returns: Persisted snapshot payload.
        :rtype: Dict[str, Any]
        :raises ValueError: When release_tag is missing.
        """
        if not release_tag:
            raise ValueError("release_tag is required to capture a snapshot")

        start_time = time.monotonic()
        table_name = str(manifest["table_name"])
        released_at = released_at or datetime.now(timezone.utc)
        columns: Sequence[ColumnDefinition] = []
        column_stats: Sequence[ColumnStat] = []
        total_rows = 0
        total_columns = 0
        schema_hash = ""
        status = "error"
        snapshot_payload: Dict[str, Any]

        try:
            columns = self._snapshots.get_columns(table_name)
            schema_hash = build_schema_hash(columns)
            total_rows = self._snapshots.get_total_rows(table_name)
            column_stats = self._snapshots.get_column_stats(
                table_name,
                columns,
                total_rows,
                top_values_columns=top_values_columns,
            )
            total_columns = len(columns)
            status = "success"
        except Exception:
            status = "error"
            raise
        finally:
            executed_at = datetime.now(timezone.utc)
            snapshot_payload = self._build_snapshot_payload(
                manifest,
                release_tag,
                release_version,
                released_at,
                executed_at,
                status,
                int((time.monotonic() - start_time) * 1000),
                total_rows,
                total_columns,
                schema_hash,
                columns,
                column_stats,
            )
            self._snapshots.create_snapshot(snapshot_payload)

        return snapshot_payload

    def compare_snapshots(
        self, base_snapshot: Mapping[str, Any], compare_snapshot: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Compare two snapshots and return drift metadata.

        :param base_snapshot: Snapshot used as the baseline.
        :type base_snapshot: Mapping[str, Any]
        :param compare_snapshot: Snapshot used for comparison.
        :type compare_snapshot: Mapping[str, Any]
        :returns: Drift payload computed from the two snapshots.
        :rtype: Dict[str, Any]
        """
        return compare_release_snapshots(base_snapshot, compare_snapshot)

    def _build_snapshot_payload(
        self,
        manifest: Mapping[str, object],
        release_tag: str,
        release_version: Optional[str],
        released_at: datetime,
        executed_at: datetime,
        status: str,
        duration_ms: int,
        total_rows: int,
        total_columns: int,
        schema_hash: str,
        columns: Sequence[ColumnDefinition],
        column_stats: Sequence[ColumnStat],
    ) -> Dict[str, Any]:
        """Build the snapshot payload for persistence.

        :param manifest: Manifest row containing metadata.
        :type manifest: Mapping[str, object]
        :param release_tag: Release tag or git SHA.
        :type release_tag: str
        :param release_version: Optional release version.
        :type release_version: Optional[str]
        :param released_at: Release timestamp.
        :type released_at: datetime
        :param executed_at: Execution timestamp for snapshot creation.
        :type executed_at: datetime
        :param status: Snapshot status string.
        :type status: str
        :param duration_ms: Execution duration in milliseconds.
        :type duration_ms: int
        :param total_rows: Total rows in the view.
        :type total_rows: int
        :param total_columns: Total columns in the view.
        :type total_columns: int
        :param schema_hash: Deterministic schema hash.
        :type schema_hash: str
        :param columns: Column definitions.
        :type columns: Sequence[ColumnDefinition]
        :param column_stats: Column stats for the view.
        :type column_stats: Sequence[ColumnStat]
        :returns: Snapshot payload dict.
        :rtype: Dict[str, Any]
        """
        return {
            "manifest_id": int(manifest["id"]),
            "table_name": str(manifest.get("table_name", "")),
            "report_name": manifest.get("report_name"),
            "agency_id": manifest.get("agency_id"),
            "agency_slug": manifest.get("agency_slug"),
            "release_tag": release_tag,
            "release_version": release_version,
            "released_at": released_at,
            "executed_at": executed_at,
            "status": status,
            "execution_duration_ms": duration_ms,
            "total_rows": total_rows,
            "total_columns": total_columns,
            "schema_hash": schema_hash,
            "columns": list(columns),
            "column_stats": list(column_stats),
        }


def build_schema_hash(columns: Sequence[ColumnDefinition]) -> str:
    """Return a deterministic hash for ordered column definitions.

    :param columns: Ordered column definitions.
    :type columns: Sequence[ColumnDefinition]
    :returns: SHA256 hex digest for the schema.
    :rtype: str
    """
    parts = [f"{col['name']}:{col['type']}" for col in columns]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest


def compare_release_snapshots(
    base_snapshot: Mapping[str, Any], compare_snapshot: Mapping[str, Any]
) -> Dict[str, Any]:
    """Compute schema and shape drift between two snapshots.

    :param base_snapshot: Baseline snapshot data.
    :type base_snapshot: Mapping[str, Any]
    :param compare_snapshot: Comparison snapshot data.
    :type compare_snapshot: Mapping[str, Any]
    :returns: Drift payload for UI consumption.
    :rtype: Dict[str, Any]
    """
    base_columns = _index_columns(base_snapshot.get("columns", []))
    compare_columns = _index_columns(compare_snapshot.get("columns", []))

    added_columns = [
        {"name": name, "type": compare_columns[name]}
        for name in sorted(compare_columns.keys() - base_columns.keys())
    ]
    removed_columns = [
        {"name": name, "type": base_columns[name]}
        for name in sorted(base_columns.keys() - compare_columns.keys())
    ]
    type_changed_columns = [
        {
            "name": name,
            "baseType": base_columns[name],
            "compareType": compare_columns[name],
        }
        for name in sorted(base_columns.keys() & compare_columns.keys())
        if base_columns[name] != compare_columns[name]
    ]
    schema_changed = bool(added_columns or removed_columns or type_changed_columns)

    base_rows = int(base_snapshot.get("total_rows") or 0)
    compare_rows = int(compare_snapshot.get("total_rows") or 0)
    row_count_delta = compare_rows - base_rows
    row_count_delta_pct = _calculate_delta_pct(base_rows, compare_rows)

    base_columns_count = int(base_snapshot.get("total_columns") or 0)
    compare_columns_count = int(compare_snapshot.get("total_columns") or 0)
    column_count_delta = compare_columns_count - base_columns_count

    column_drifts = _compare_column_stats(
        base_snapshot.get("column_stats", []),
        compare_snapshot.get("column_stats", []),
    )

    overall_drift_score = _calculate_overall_drift_score(
        schema_changed,
        row_count_delta_pct,
        column_drifts,
    )

    return {
        "schemaChanged": schema_changed,
        "addedColumns": added_columns,
        "removedColumns": removed_columns,
        "typeChangedColumns": type_changed_columns,
        "rowCountDelta": row_count_delta,
        "rowCountDeltaPct": row_count_delta_pct,
        "columnCountDelta": column_count_delta,
        "columnDrifts": column_drifts,
        "overallDriftScore": overall_drift_score,
    }


def _index_columns(columns: Iterable[Mapping[str, Any]]) -> Dict[str, str]:
    """Create a column name -> type mapping.

    :param columns: Iterable of column definitions.
    :type columns: Iterable[Mapping[str, Any]]
    :returns: Mapping of column names to types.
    :rtype: Dict[str, str]
    """
    mapping: Dict[str, str] = {}
    for column in columns:
        name = str(column.get("name", ""))
        if not name:
            continue
        mapping[name] = str(column.get("type", ""))
    return mapping


def _compare_column_stats(
    base_stats: Iterable[Mapping[str, Any]],
    compare_stats: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Compare per-column stats between snapshots.

    :param base_stats: Baseline column stats.
    :type base_stats: Iterable[Mapping[str, Any]]
    :param compare_stats: Comparison column stats.
    :type compare_stats: Iterable[Mapping[str, Any]]
    :returns: List of column drift entries.
    :rtype: List[Dict[str, Any]]
    """
    base_index = {str(stat.get("name", "")): stat for stat in base_stats if stat.get("name")}
    compare_index = {str(stat.get("name", "")): stat for stat in compare_stats if stat.get("name")}
    shared_columns = base_index.keys() & compare_index.keys()

    drifts: List[Dict[str, Any]] = []
    for column in sorted(shared_columns):
        base_stat = base_index[column]
        compare_stat = compare_index[column]
        base_null_pct = float(base_stat.get("null_pct") or 0.0)
        compare_null_pct = float(compare_stat.get("null_pct") or 0.0)
        base_distinct = int(base_stat.get("distinct_count") or 0)
        compare_distinct = int(compare_stat.get("distinct_count") or 0)

        drift: Dict[str, Any] = {
            "column": column,
            "baseNullPct": base_null_pct,
            "compareNullPct": compare_null_pct,
            "nullPctDelta": compare_null_pct - base_null_pct,
            "baseDistinctCount": base_distinct,
            "compareDistinctCount": compare_distinct,
            "distinctDelta": compare_distinct - base_distinct,
        }

        min_delta, max_delta = _compute_min_max_delta(
            base_stat.get("min"),
            compare_stat.get("min"),
            base_stat.get("max"),
            compare_stat.get("max"),
        )
        if min_delta is not None:
            drift["minDelta"] = min_delta
        if max_delta is not None:
            drift["maxDelta"] = max_delta

        base_top = base_stat.get("top_values")
        compare_top = compare_stat.get("top_values")
        if base_top or compare_top:
            drift["topValues"] = {"base": base_top or [], "compare": compare_top or []}

        drifts.append(drift)

    return drifts


def _compute_min_max_delta(
    base_min: Any, compare_min: Any, base_max: Any, compare_max: Any
) -> Tuple[Optional[float], Optional[float]]:
    """Compute numeric deltas for min/max when possible.

    :param base_min: Baseline minimum value.
    :type base_min: Any
    :param compare_min: Comparison minimum value.
    :type compare_min: Any
    :param base_max: Baseline maximum value.
    :type base_max: Any
    :param compare_max: Comparison maximum value.
    :type compare_max: Any
    :returns: Tuple of min delta and max delta (None when not numeric).
    :rtype: Tuple[Optional[float], Optional[float]]
    """
    return (_numeric_delta(base_min, compare_min), _numeric_delta(base_max, compare_max))


def _numeric_delta(base_value: Any, compare_value: Any) -> Optional[float]:
    """Compute delta between two numeric values.

    :param base_value: Baseline value.
    :type base_value: Any
    :param compare_value: Comparison value.
    :type compare_value: Any
    :returns: Difference as float or None when not numeric.
    :rtype: Optional[float]
    """
    try:
        return float(compare_value) - float(base_value)
    except (TypeError, ValueError):
        return None


def _calculate_delta_pct(base_value: int, compare_value: int) -> float:
    """Return percentage delta between two values, handling divide-by-zero.

    :param base_value: Baseline value.
    :type base_value: int
    :param compare_value: Comparison value.
    :type compare_value: int
    :returns: Delta percentage.
    :rtype: float
    """
    if base_value == 0:
        return 0.0 if compare_value == 0 else ZERO_BASE_DELTA_PCT
    return (compare_value - base_value) / base_value * 100.0


def _calculate_overall_drift_score(
    schema_changed: bool, row_delta_pct: float, column_drifts: Sequence[Mapping[str, Any]]
) -> float:
    """Compute a heuristic drift score.

    The heuristic is intentionally simple for v1:
    - Start at 0.
    - Add 30 points for any schema change.
    - Add 10/20/30 points based on absolute row delta percentage thresholds.
    - Add 2 points for each column with a null-pct delta >= 10.
    - Add 2 points for each column with a distinct delta >= 10.

    :param schema_changed: Whether schema drift was detected.
    :type schema_changed: bool
    :param row_delta_pct: Row count delta percentage.
    :type row_delta_pct: float
    :param column_drifts: Column drift entries.
    :type column_drifts: Sequence[Mapping[str, Any]]
    :returns: Drift score.
    :rtype: float
    """
    score = 0.0
    if schema_changed:
        score += 30.0

    abs_row_delta = abs(row_delta_pct)
    if abs_row_delta >= 50:
        score += 30.0
    elif abs_row_delta >= 25:
        score += 20.0
    elif abs_row_delta >= 10:
        score += 10.0

    for drift in column_drifts:
        null_delta = abs(float(drift.get("nullPctDelta") or 0.0))
        distinct_delta = abs(float(drift.get("distinctDelta") or 0.0))
        if null_delta >= 10:
            score += 2.0
        if distinct_delta >= 10:
            score += 2.0

    return score
