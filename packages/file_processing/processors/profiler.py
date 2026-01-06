"""Data profiler for generating profile payloads.

This module generates statistical summaries, distributions, and sample data
for the data quality pipeline.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

from file_processing.models.quality import ProfilePayload, SampleData

logger = logging.getLogger(__name__)


class DataProfiler:
    """Generates data profiling payloads for parsed file data.

    Computes:
    - Statistical summaries (count, min, max, mean for numeric columns)
    - Completeness overview (null counts per column)
    - Type/format issues
    - Uniqueness overview
    - Value distributions
    - Bounds anomalies
    - Sample data rows
    """

    MAX_SAMPLE_ROWS: int = 20
    MAX_DISTRIBUTION_ITEMS: int = 25
    MAX_ANOMALY_EXAMPLES: int = 25

    def __init__(
        self,
        max_sample_rows: int = MAX_SAMPLE_ROWS,
        max_distribution_items: int = MAX_DISTRIBUTION_ITEMS,
    ) -> None:
        """Initialize the profiler.

        Args:
            max_sample_rows: Maximum sample rows to include.
            max_distribution_items: Maximum distribution items per column.
        """
        self._max_sample_rows = max_sample_rows
        self._max_distribution_items = max_distribution_items

    def generate_profile(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        schema_definition: Optional[Dict[str, Any]] = None,
    ) -> ProfilePayload:
        """Generate a complete profile payload.

        Args:
            rows: Parsed data rows.
            columns: Column names.
            schema_definition: Optional schema definition for type info.

        Returns:
            ProfilePayload with all profiling data.
        """
        if not rows or not columns:
            return ProfilePayload()

        profile = ProfilePayload(
            statistical_summary=self._compute_statistical_summary(rows, columns),
            completeness_overview=self._compute_completeness(rows, columns),
            type_format_issues=self._detect_type_issues(rows, columns, schema_definition),
            uniqueness_overview=self._compute_uniqueness(rows, columns),
            value_distributions=self._compute_distributions(rows, columns),
            bounds_anomalies=self._detect_bounds_anomalies(rows, columns, schema_definition),
            sample_data=self._extract_sample_data(rows, columns),
        )

        return profile

    def _compute_statistical_summary(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
    ) -> Dict[str, Any]:
        """Compute statistical summary for numeric columns.

        Args:
            rows: Data rows.
            columns: Column names.

        Returns:
            Dictionary with column statistics.
        """
        summary: Dict[str, Any] = {
            "totalRows": len(rows),
            "totalColumns": len(columns),
            "columns": {},
        }

        for col in columns:
            values = [row.get(col) for row in rows if row.get(col) is not None]
            col_summary: Dict[str, Any] = {
                "count": len(values),
                "nullCount": len(rows) - len(values),
            }

            # Try to compute numeric stats
            numeric_values: List[float] = []
            for v in values:
                try:
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        numeric_values.append(float(v))
                    elif isinstance(v, str):
                        numeric_values.append(float(v))
                except (ValueError, TypeError):
                    pass

            if numeric_values:
                col_summary["min"] = min(numeric_values)
                col_summary["max"] = max(numeric_values)
                col_summary["mean"] = sum(numeric_values) / len(numeric_values)
                col_summary["isNumeric"] = True
            else:
                col_summary["isNumeric"] = False

            summary["columns"][col] = col_summary

        return summary

    def _compute_completeness(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
    ) -> Dict[str, Any]:
        """Compute completeness overview.

        Args:
            rows: Data rows.
            columns: Column names.

        Returns:
            Dictionary with completeness stats per column.
        """
        overview: Dict[str, Any] = {
            "totalRows": len(rows),
            "columns": {},
        }

        total_cells = len(rows) * len(columns)
        total_nulls = 0

        for col in columns:
            null_count = sum(
                1 for row in rows
                if row.get(col) is None or (isinstance(row.get(col), str) and row.get(col).strip() == "")
            )
            total_nulls += null_count

            pct = 100.0 * (len(rows) - null_count) / len(rows) if rows else 100.0
            overview["columns"][col] = {
                "nullCount": null_count,
                "completenessPercent": round(pct, 2),
            }

        overview["overallCompleteness"] = round(
            100.0 * (total_cells - total_nulls) / total_cells if total_cells > 0 else 100.0, 2
        )

        return overview

    def _detect_type_issues(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        schema_definition: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Detect type/format issues in the data.

        Args:
            rows: Data rows.
            columns: Column names.
            schema_definition: Optional schema definition.

        Returns:
            List of detected issues.
        """
        issues: List[Dict[str, Any]] = []

        if not schema_definition:
            return issues

        column_types: Dict[str, str] = {}
        for col_def in schema_definition.get("columns", []):
            col_name = col_def.get("name", "")
            col_type = col_def.get("type", "").lower()
            if col_name and col_type:
                column_types[col_name] = col_type

        sample_rows = rows[:100]
        for col, expected_type in column_types.items():
            if col not in columns:
                continue

            mismatches = 0
            examples: List[str] = []

            for row in sample_rows:
                value = row.get(col)
                if value is None:
                    continue

                matches, reason = self._value_matches_type(value, expected_type)
                if not matches:
                    mismatches += 1
                    if len(examples) < 3:
                        examples.append(f"{str(value)[:50]} (Reason: {reason})")

            if mismatches > 0:
                issues.append({
                    "column": col,
                    "expectedType": expected_type,
                    "mismatchCount": mismatches,
                    "examples": examples,
                })

        return issues[:self.MAX_ANOMALY_EXAMPLES]

    def _value_matches_type(self, value: Any, expected_type: str) -> Tuple[bool, Optional[str]]:
        """Check if value matches expected type and return reason if not."""
        if expected_type in ("string", "str", "text"):
            if isinstance(value, str):
                return True, None
            return False, f"Expected string, got {type(value).__name__}"

        if expected_type in ("integer", "int"):
            if isinstance(value, bool):
                return False, "Boolean value not allowed for integer"
            if isinstance(value, int):
                return True, None
            if isinstance(value, str):
                try:
                    int(value)
                    return True, None
                except ValueError:
                    return False, f"String '{value}' cannot be parsed as integer"
            return False, f"Expected integer, got {type(value).__name__}"

        if expected_type in ("float", "number", "decimal"):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return True, None
            if isinstance(value, str):
                try:
                    float(value)
                    return True, None
                except ValueError:
                    return False, f"String '{value}' cannot be parsed as float"
            return False, f"Expected number, got {type(value).__name__}"

        if expected_type in ("boolean", "bool"):
            if isinstance(value, bool):
                return True, None
            if isinstance(value, str) and value.lower() in ("true", "false", "1", "0"):
                return True, None
            return False, f"Value '{value}' is not a valid boolean"

        return True, None

    def _compute_uniqueness(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
    ) -> Dict[str, Any]:
        """Compute uniqueness overview per column.

        Args:
            rows: Data rows.
            columns: Column names.

        Returns:
            Dictionary with uniqueness stats.
        """
        overview: Dict[str, Any] = {
            "columns": {},
        }

        for col in columns:
            values = [row.get(col) for row in rows if row.get(col) is not None]
            unique_count = len(set(values))
            total_count = len(values)

            uniqueness_ratio = unique_count / total_count if total_count > 0 else 1.0

            overview["columns"][col] = {
                "uniqueCount": unique_count,
                "totalCount": total_count,
                "uniquenessRatio": round(uniqueness_ratio, 4),
                "isUnique": uniqueness_ratio == 1.0,
            }

        return overview

    def _compute_distributions(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Compute value distributions for categorical columns.

        Args:
            rows: Data rows.
            columns: Column names.

        Returns:
            Dictionary mapping column name to distribution list.
        """
        distributions: Dict[str, List[Dict[str, Any]]] = {}

        for col in columns:
            values = [row.get(col) for row in rows if row.get(col) is not None]

            # Skip if too many unique values (likely not categorical)
            unique_count = len(set(values))
            if unique_count > 100 or unique_count == len(values):
                continue

            counter = Counter(values)
            most_common = counter.most_common(self._max_distribution_items)

            dist_list: List[Dict[str, Any]] = []
            for value, count in most_common:
                pct = 100.0 * count / len(values) if values else 0.0
                dist_list.append({
                    "value": str(value)[:100],
                    "count": count,
                    "percent": round(pct, 2),
                })

            if dist_list:
                distributions[col] = dist_list

        return distributions

    def _detect_bounds_anomalies(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        schema_definition: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Detect values outside expected bounds.

        Args:
            rows: Data rows.
            columns: Column names.
            schema_definition: Optional schema definition with bounds.

        Returns:
            List of detected anomalies.
        """
        anomalies: List[Dict[str, Any]] = []

        if not schema_definition:
            return anomalies

        for col_def in schema_definition.get("columns", []):
            col_name = col_def.get("name", "")
            min_val = col_def.get("min")
            max_val = col_def.get("max")

            if col_name not in columns or (min_val is None and max_val is None):
                continue

            for row_idx, row in enumerate(rows[:100]):
                value = row.get(col_name)
                if value is None:
                    continue

                try:
                    num_val = float(value)
                    is_anomaly = False
                    reason = ""

                    if min_val is not None and num_val < float(min_val):
                        is_anomaly = True
                        reason = f"below min ({min_val})"

                    if max_val is not None and num_val > float(max_val):
                        is_anomaly = True
                        reason = f"above max ({max_val})"

                    if is_anomaly:
                        anomalies.append({
                            "column": col_name,
                            "row": row_idx + 1,
                            "value": value,
                            "reason": reason,
                        })

                        if len(anomalies) >= self.MAX_ANOMALY_EXAMPLES:
                            return anomalies

                except (ValueError, TypeError):
                    pass

        return anomalies

    def _extract_sample_data(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
    ) -> SampleData:
        """Extract sample rows for the profile.

        Args:
            rows: Data rows.
            columns: Column names.

        Returns:
            SampleData with columns and sample rows.
        """
        sample_rows = rows[:self._max_sample_rows]

        # Convert to list of lists format
        row_data: List[List[Any]] = []
        for row in sample_rows:
            row_list = [row.get(col) for col in columns]
            row_data.append(row_list)

        return SampleData(
            columns=columns,
            rows=row_data,
        )
