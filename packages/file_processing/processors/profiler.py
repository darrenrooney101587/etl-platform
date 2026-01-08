"""Data profiler for generating profile payloads.

This module generates statistical summaries, distributions, and sample data
for the data quality pipeline.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

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
        # Null definition: treat None, empty string, and literal 'null' (case-insensitive) as null
        # Exposed as a helper so all profiling functions use consistent logic.
    def _is_null(self, v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return True
            if s.lower() == "null":
                return True
        return False

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
            uniqueness_overview=self._compute_uniqueness(rows, columns, schema_definition),
            value_distributions=self._compute_distributions(rows, columns),
            bounds_anomalies=self._detect_bounds_anomalies(rows, columns, schema_definition),
            sample_data=self._extract_sample_data(rows, columns),
        )

        return profile

    def _compute_statistical_summary(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        schema_definition: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Compute statistical summary for numeric columns.

        Only computes statistics if:
        1. The schema explicitly defines the column as numeric (int, float, etc.), OR
        2. No schema type is defined, but >80% of non-null values are numeric.

        Args:
            rows: Data rows.
            columns: Column names.

        Returns:
            List of dictionaries with column statistics.
        """
        import statistics


        summary: List[Dict[str, Any]] = []

        # Pre-fetch column types if schema is available
        col_types = {}
        if schema_definition:
            for col_def in schema_definition.get("columns", []):
                if "name" in col_def and "type" in col_def:
                    col_types[col_def["name"]] = col_def["type"].lower()

        numeric_type_aliases = (
            "integer", "int", "int4", "int8", "bigint",
            "float", "number", "decimal", "double", "real", "numeric"
        )

        for col in columns:
             # 1. Check schema if available
             defined_type = col_types.get(col)
             if defined_type:
                 # If schema says strict string/bool/date, skip stats
                 if defined_type not in numeric_type_aliases:
                     continue

             # Collect non-null values for this column
             non_null_vals = [row.get(col) for row in rows if not self._is_null(row.get(col))]

             if not non_null_vals:
                 continue

             # Convert to numeric values
             numeric_values: List[float] = []
             for v in non_null_vals:
                 try:
                     if isinstance(v, (int, float)) and not isinstance(v, bool):
                         numeric_values.append(float(v))
                     elif isinstance(v, str):
                         numeric_values.append(float(v))
                 except (ValueError, TypeError):
                     pass

             if not numeric_values:
                 continue

             # 2. Heuristic: if no schema enforced, ensure > 80% of data is numeric
             # to avoid generating stats for string columns with occasional dirty numbers.
             if not defined_type:
                 numeric_ratio = len(numeric_values) / len(non_null_vals)
                 if numeric_ratio < 0.8:
                     continue

             count = len(numeric_values)
             min_val = min(numeric_values)
             max_val = max(numeric_values)
             mean_val = statistics.mean(numeric_values)
             median_val = statistics.median(numeric_values)
             std_dev = statistics.stdev(numeric_values) if count > 1 else 0.0

             zeros = sum(1 for x in numeric_values if x == 0)
             negatives = sum(1 for x in numeric_values if x < 0)

             # Outliers
             numeric_values_sorted = sorted(numeric_values)
             q1 = numeric_values_sorted[int(count * 0.25)]
             q3 = numeric_values_sorted[int(count * 0.75)]
             iqr = q3 - q1
             lower_bound = q1 - 1.5 * iqr
             upper_bound = q3 + 1.5 * iqr

             outliers = [x for x in numeric_values if x < lower_bound or x > upper_bound]
             outlier_count = len(outliers)
             # Sample up to 10 outliers
             outlier_values = outliers[:10]

             # Simple distribution heuristic
             distribution = "unknown"
             if abs(mean_val - median_val) < (iqr * 0.1) if iqr > 0 else True:
                 distribution = "normal"
             elif mean_val > median_val:
                 distribution = "skewed-right"
             else:
                 distribution = "skewed-left"

             summary.append({
                 "column": col,
                 "mean": round(mean_val, 2),
                 "median": round(median_val, 2),
                 "stdDev": round(std_dev, 2),
                 "min": min_val,
                 "max": max_val,
                 "count": count,
                 "zeros": zeros,
                 "negatives": negatives,
                 "distribution": distribution,
                 "outlierCount": outlier_count,
                 "outlierValues": outlier_values,
             })

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
            Dictionary with completeness stats.
        """
        total_rows = len(rows)
        if total_rows == 0:
            return {
                "totalRows": 0,
                "completeRows": 0,
                "completeRowPercentage": 0.0,
                "entirelyNullColumns": [],
                "columnsWithNulls": [],
            }

        complete_rows = 0
        columns_null_counts = {col: 0 for col in columns}

        for row in rows:
            is_complete = True
            for col in columns:
                val = row.get(col)
                is_null = self._is_null(val)
                if is_null:
                    columns_null_counts[col] += 1
                    is_complete = False
            if is_complete:
                complete_rows += 1

        complete_row_pct = round(100.0 * complete_rows / total_rows, 2)
        entirely_null_cols = [col for col, count in columns_null_counts.items() if count == total_rows]
        columns_with_nulls = [
            {
                "column": col,
                "nulls": count,
                "nullPercentage": round(100.0 * count / total_rows, 2)
            }
            for col, count in columns_null_counts.items() if count > 0
        ]

        return {
            "totalRows": total_rows,
            "completeRows": complete_rows,
            "completeRowPercentage": complete_row_pct,
            "entirelyNullColumns": entirely_null_cols,
            "columnsWithNulls": columns_with_nulls,
        }

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

        # Check all rows, or a significant sample if limited
        check_rows = rows[:1000]
        total_checked = len(check_rows)

        if total_checked == 0:
            return []

        for col, expected_type in column_types.items():
            if col not in columns:
                continue

            mismatches = 0
            examples: List[str] = []

            # Simple heuristic for actual type
            observed_types = Counter()

            for row in check_rows:
                value = row.get(col)
                if self._is_null(value):
                    continue

                matches, reason = self._value_matches_type(value, expected_type)
                if not matches:
                    mismatches += 1
                    observed_types[type(value).__name__] += 1
                    if len(examples) < 5:
                        val_str = str(value)
                        if val_str not in examples:
                            examples.append(val_str)

            if mismatches > 0:
                most_common_type = observed_types.most_common(1)
                actual_type = most_common_type[0][0] if most_common_type else "unknown"

                issues.append({
                    "column": col,
                    "expectedType": expected_type,
                    "actualType": actual_type,
                    "invalidCount": mismatches,
                    "invalidPercentage": round(100.0 * mismatches / total_checked, 2),
                    "sampleInvalid": examples,
                })

        return issues[:self.MAX_ANOMALY_EXAMPLES]

    def _value_matches_type(self, value: Any, expected_type: str) -> Tuple[bool, Optional[str]]:
        """Check if value matches expected type and return reason if not."""
        if expected_type in ("string", "str", "text", "varchar"):
            if isinstance(value, str):
                return True, None
            return False, f"Expected string, got {type(value).__name__}"

        if expected_type in ("integer", "int", "int4", "int8", "bigint"):
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

        if expected_type in ("float", "number", "decimal", "double", "real", "numeric"):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return True, None
            if isinstance(value, str):
                try:
                    float(value)
                    return True, None
                except ValueError:
                    return False, f"String '{value}' cannot be parsed as float"
            return False, f"Expected number, got {type(value).__name__}"

        if expected_type in ("boolean", "bool", "bit"):
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
        schema_definition: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compute uniqueness overview per column.

        Args:
            rows: Data rows.
            columns: Column names.
            schema_definition: Optional schema to identify identity/primary key columns.

        Returns:
            Dictionary with uniqueness stats.
        """
        total_rows = len(rows)
        if total_rows == 0:
            return {
                "totalRows": 0,
                "uniqueRows": 0,
                "duplicateRows": 0,
                "duplicatePercentage": 0.0,
                "columns": [],
            }

        # Identify "Identity" columns to exclude from duplicate row detection.
        # Business duplicates should be counted based on data columns, ignoring technical IDs.
        identity_cols: set[str] = set()

        if schema_definition:
            for col_def in schema_definition.get("columns", []):
                name = col_def.get("name")
                if not name:
                    continue
                # Criteria for identity column:
                # 1. explicitly marked as identity
                is_identity = col_def.get("identity", False)

                if is_identity:
                    identity_cols.add(name)

        # Determine data columns (all columns minus identity columns)
        # If all columns are identity columns (edge case), fall back to using all columns
        # to avoid empty tuple uniqueness checking (which would flag 100% duplicates).
        data_cols = [c for c in columns if c not in identity_cols]
        if not data_cols:
            data_cols = columns

        # Check for row duplicates based on data columns
        row_tuples = [tuple(row.get(col) for col in data_cols) for row in rows]
        unique_rows_set = set(row_tuples)
        unique_rows_count = len(unique_rows_set)
        duplicate_rows = total_rows - unique_rows_count
        duplicate_percentage = round(100.0 * duplicate_rows / total_rows, 2)

        column_stats = []
        for col in columns:
            values = [row.get(col) for row in rows if not self._is_null(row.get(col))]
            val_total = len(values)
            unique_count = len(set(values))

            # Cardinality as percentage 0-100
            cardinality = round(100.0 * unique_count / val_total, 2) if val_total > 0 else 0.0

            # Per-column duplicate rows: count of values that occur more than once (sum of counts for value>1)
            from collections import Counter

            counter = Counter(values)
            duplicate_count_col = sum(count for count in counter.values() if count > 1)
            duplicate_percentage_col = round(100.0 * duplicate_count_col / len(rows), 2) if len(rows) > 0 else 0.0

            column_stats.append({
                "column": col,
                "uniqueCount": unique_count,
                "cardinality": cardinality,
                "duplicateCount": duplicate_count_col,
                "duplicatePercentage": duplicate_percentage_col,
            })

        return {
            "totalRows": total_rows,
            "uniqueRows": unique_rows_count,
            "duplicateRows": duplicate_rows,
            "duplicatePercentage": duplicate_percentage,
            "columns": column_stats,
        }

    def _compute_distributions(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
    ) -> List[Dict[str, Any]]:
        """Compute value distributions for categorical columns.

        Args:
            rows: Data rows.
            columns: Column names.

        Returns:
            List of objects containing histogram data.
        """
        distributions: List[Dict[str, Any]] = []

        for col in columns:
            values = [row.get(col) for row in rows if not self._is_null(row.get(col))]
            if not values:
                continue

            unique_count = len(set(values))
            # Heuristic: treat as categorical if unique count is low relative to row count
            # or absolute count is small
            total_rows = len(values)
            is_categorical = unique_count <= 20 or (unique_count < total_rows * 0.1 and unique_count < 100)

            if not is_categorical:
                continue

            counter = Counter(values)
            most_common = counter.most_common(self._max_distribution_items)

            histogram: List[Dict[str, Any]] = []
            for value, count in most_common:
                histogram.append({
                    "bin": str(value)[:50],
                    "count": count,
                })

            distributions.append({
                "column": col,
                "histogram": histogram
            })

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

            outliers: List[float] = []

            for row in rows[:1000]: # Check reasonable sample
                value = row.get(col_name)
                if self._is_null(value):
                    continue

                try:
                    num_val = float(value)
                    is_anomaly = False

                    if min_val is not None and num_val < float(min_val):
                        is_anomaly = True

                    if max_val is not None and num_val > float(max_val):
                        is_anomaly = True

                    if is_anomaly:
                        outliers.append(num_val)

                except (ValueError, TypeError):
                    pass

            if outliers:
                anomalies.append({
                    "column": col_name,
                    "severity": "Medium", # Default
                    "lowerBound": min_val,
                    "upperBound": max_val,
                    "outliersCount": len(outliers),
                    "exampleValues": outliers[:5]
                })

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
