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
        # Fraction of non-null values that must be numeric to treat column as numeric
        self._numeric_fraction_threshold = 0.5

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
    ) -> List[Dict[str, Any]]:
        """Compute statistical summary for numeric columns.

        Args:
            rows: Data rows.
            columns: Column names.

        Returns:
            List of dictionaries with column statistics.
        """
        import statistics

        summary: List[Dict[str, Any]] = []

        for col in columns:
            # Collect non-null values for this column
            non_null_vals = [row.get(col) for row in rows if row.get(col) is not None and row.get(col) != ""]

            # Attempt to coerce to numeric for each value
            numeric_values: List[float] = []
            for v in non_null_vals:
                num = self._coerce_number(v)
                if num is not None:
                    numeric_values.append(num)

            total_non_null = len(non_null_vals)
            num_count = len(numeric_values)
            numeric_fraction = (num_count / total_non_null) if total_non_null > 0 else 0.0

            # If enough values are numeric, compute numeric stats
            if num_count > 0 and numeric_fraction >= self._numeric_fraction_threshold:
                count = num_count
                min_val = min(numeric_values)
                max_val = max(numeric_values)
                mean_val = statistics.mean(numeric_values)
                median_val = statistics.median(numeric_values)
                std_dev = statistics.stdev(numeric_values) if count > 1 else 0.0

                zeros = sum(1 for x in numeric_values if x == 0)
                negatives = sum(1 for x in numeric_values if x < 0)

                # IQR and Outliers
                numeric_values_sorted = sorted(numeric_values)
                q1 = numeric_values_sorted[int(count * 0.25)]
                q3 = numeric_values_sorted[int(count * 0.75)]
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr

                outliers = [x for x in numeric_values if x < lower_bound or x > upper_bound]
                outlier_count = len(outliers)
                outlier_values = outliers[:10]

                # Simple distribution heuristic
                distribution = "unknown"
                if iqr > 0 and abs(mean_val - median_val) < (iqr * 0.1):
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
                    "iqr": round(iqr, 2),
                    "distribution": distribution,
                    "outlierCount": outlier_count,
                    "outlierValues": outlier_values,
                    "numericFraction": round(numeric_fraction, 3),
                    "nonNumericCount": total_non_null - num_count,
                })
            else:
                # Non-numeric or mixed column: emit categorical summary
                vals = non_null_vals
                total = len(vals)
                unique_count = len(set(vals))
                cardinality = round(100.0 * unique_count / total, 2) if total > 0 else 0.0
                counter = Counter(vals)
                top = counter.most_common(10)
                top_list = [{"value": k, "count": c} for k, c in top]

                summary.append({
                    "column": col,
                    "type": "categorical",
                    "count": total,
                    "uniqueCount": unique_count,
                    "cardinality": cardinality,
                    "topValues": top_list,
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
                is_null = val is None or (isinstance(val, str) and val.strip() == "")
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
                if value is None:
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
        total_rows = len(rows)
        if total_rows == 0:
            return {
                "totalRows": 0,
                "uniqueRows": 0,
                "duplicateRows": 0,
                "duplicatePercentage": 0.0,
                "columns": [],
            }

        # Check for full row duplicates (expensive but requested)
        # Convert rows to tuple of values for hashing
        row_tuples = [tuple(row.get(col) for col in columns) for row in rows]
        unique_rows_set = set(row_tuples)
        unique_rows_count = len(unique_rows_set)
        duplicate_rows = total_rows - unique_rows_count
        duplicate_percentage = round(100.0 * duplicate_rows / total_rows, 2)

        column_stats = []
        for col in columns:
            values = [row.get(col) for row in rows if row.get(col) is not None]
            val_total = len(values)
            unique_count = len(set(values))

            # Cardinality as percentage 0-100
            cardinality = round(100.0 * unique_count / val_total, 2) if val_total > 0 else 0.0

            column_stats.append({
                "column": col,
                "uniqueCount": unique_count,
                "cardinality": cardinality,
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
            values = [row.get(col) for row in rows if row.get(col) is not None]
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
                if value is None:
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

    def _coerce_number(self, value: Any) -> Optional[float]:
        """Coerce value to a number, handling various formats.

        Args:
            value: The value to coerce.

        Returns:
            The coerced number, or None if coercion failed.
        """
        if value is None:
            return None

        # Handle common numeric formats
        value_str = str(value).strip()

        # Remove percent sign and convert to float
        if value_str.endswith("%"):
            try:
                return float(value_str[:-1]) / 100.0
            except ValueError:
                return None

        # Remove currency symbols and commas, convert to float
        for prefix in ("$", "£", "€"):
            if value_str.startswith(prefix):
                value_str = value_str[len(prefix):]
                break

        value_str = value_str.replace(",", "")

        try:
            return float(value_str)
        except ValueError:
            return None
