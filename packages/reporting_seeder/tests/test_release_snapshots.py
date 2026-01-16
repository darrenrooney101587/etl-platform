"""Unit tests for release snapshot hashing and drift comparison."""
from __future__ import annotations

import unittest
from typing import Any, Dict

from reporting_seeder.processors.release_snapshots import (
    build_schema_hash,
    compare_release_snapshots,
)


class ReleaseSnapshotTests(unittest.TestCase):
    """Tests for release snapshot helpers."""

    def test_schema_hash_ordering_is_stable(self) -> None:
        """Ensure schema hash changes when column order changes."""
        columns_a = [{"name": "id", "type": "integer"}, {"name": "name", "type": "text"}]
        columns_b = [{"name": "name", "type": "text"}, {"name": "id", "type": "integer"}]

        self.assertEqual(build_schema_hash(columns_a), build_schema_hash(columns_a))
        self.assertNotEqual(build_schema_hash(columns_a), build_schema_hash(columns_b))

    def test_compare_detects_schema_and_shape_drift(self) -> None:
        """Validate schema drift and column stat deltas."""
        base_snapshot = _make_snapshot(
            columns=[{"name": "id", "type": "integer"}, {"name": "status", "type": "text"}],
            stats=[
                {"name": "id", "type": "integer", "null_pct": 0.0, "distinct_count": 10, "min": 1, "max": 10},
                {"name": "status", "type": "text", "null_pct": 10.0, "distinct_count": 2},
            ],
            total_rows=100,
        )
        compare_snapshot = _make_snapshot(
            columns=[
                {"name": "id", "type": "integer"},
                {"name": "status", "type": "varchar"},
                {"name": "priority", "type": "text"},
            ],
            stats=[
                {"name": "id", "type": "integer", "null_pct": 5.0, "distinct_count": 12, "min": 1, "max": 12},
                {"name": "status", "type": "varchar", "null_pct": 20.0, "distinct_count": 3},
            ],
            total_rows=120,
        )

        drift = compare_release_snapshots(base_snapshot, compare_snapshot)
        self.assertTrue(drift["schemaChanged"])
        self.assertEqual([{"name": "priority", "type": "text"}], drift["addedColumns"])
        self.assertEqual(
            [{"name": "status", "baseType": "text", "compareType": "varchar"}],
            drift["typeChangedColumns"],
        )
        self.assertEqual(20, drift["rowCountDelta"])
        self.assertEqual(1, drift["columnCountDelta"])

        status_drift = next(entry for entry in drift["columnDrifts"] if entry["column"] == "status")
        self.assertEqual(10.0, status_drift["nullPctDelta"])
        self.assertEqual(1, status_drift["distinctDelta"])

    def test_compare_handles_zero_base_row_count(self) -> None:
        """Ensure row delta pct handles divide-by-zero."""
        base_snapshot = _make_snapshot(
            columns=[{"name": "id", "type": "integer"}],
            stats=[{"name": "id", "type": "integer", "null_pct": 0.0, "distinct_count": 0}],
            total_rows=0,
        )
        compare_snapshot = _make_snapshot(
            columns=[{"name": "id", "type": "integer"}],
            stats=[{"name": "id", "type": "integer", "null_pct": 0.0, "distinct_count": 5}],
            total_rows=5,
        )

        drift = compare_release_snapshots(base_snapshot, compare_snapshot)
        self.assertEqual(5, drift["rowCountDelta"])
        self.assertEqual(100.0, drift["rowCountDeltaPct"])


def _make_snapshot(
    columns: list[Dict[str, Any]],
    stats: list[Dict[str, Any]],
    total_rows: int,
    total_columns: int | None = None,
) -> Dict[str, Any]:
    """Build a minimal snapshot dict for tests.

    :param columns: Column definitions.
    :type columns: list
    :param stats: Column stats.
    :type stats: list
    :param total_rows: Total rows in the snapshot.
    :type total_rows: int
    :param total_columns: Optional override for total columns.
    :type total_columns: int | None
    :returns: Snapshot dict used by drift comparisons.
    :rtype: Dict[str, Any]
    """
    return {
        "columns": columns,
        "column_stats": stats,
        "total_rows": total_rows,
        "total_columns": total_columns if total_columns is not None else len(columns),
    }


if __name__ == "__main__":
    unittest.main()
