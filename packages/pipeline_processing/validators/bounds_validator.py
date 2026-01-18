"""Bounds validation for data files.

Validates that numeric and date values fall within declared bounds.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

from pipeline_processing.validators.base import BaseValidator, ValidationResult

logger = logging.getLogger(__name__)


class BoundsValidator(BaseValidator):
    """Validator for value bounds/range constraints.

    Checks that values fall within declared min/max bounds.
    """

    @property
    def validator_name(self) -> str:
        """Return the validator name."""
        return "bounds"

    def validate(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        schema_definition: Dict[str, Any],
    ) -> ValidationResult:
        """Validate that values fall within declared bounds.

        Schema definition expected format:
        {
            "columns": [
                {"name": "age", "type": "integer", "min": 0, "max": 150},
                {"name": "price", "type": "float", "min": 0.0},
                {"name": "created_date", "type": "date", "min": "2020-01-01"},
                ...
            ]
        }

        Args:
            rows: Parsed data rows.
            columns: Column names from the file.
            schema_definition: Schema definition JSON.

        Returns:
            ValidationResult with bounds check details.
        """
        if not rows:
            return ValidationResult(
                passed=True,
                details="No rows to validate",
                metadata={"row_count": 0},
            )

        bounded_columns = self._get_bounded_columns(schema_definition, columns)

        if not bounded_columns:
            return ValidationResult(
                passed=True,
                details="No bounds defined; skipping bounds validation",
                metadata={"row_count": len(rows)},
            )

        failures: List[Dict[str, Any]] = []
        total_checks = 0
        total_violations = 0

        for col_name, bounds in bounded_columns.items():
            result = self._check_bounds(rows, col_name, bounds)
            total_checks += result["checked_count"]
            total_violations += result["violation_count"]

            if result["violation_count"] > 0:
                failures.append({
                    "check": "bounds",
                    "column": col_name,
                    "bounds": bounds,
                    "checked_count": result["checked_count"],
                    "violation_count": result["violation_count"],
                    "below_min": result["below_min"],
                    "above_max": result["above_max"],
                    "sample_violations": result["sample_violations"][:10],
                    "message": f"Column '{col_name}' has {result['violation_count']} values outside bounds",
                })

        passed = total_violations == 0

        if passed:
            details = f"All {len(bounded_columns)} bounded columns validated across {len(rows)} rows"
        else:
            pct_in_bounds = 100.0 * (1 - total_violations / total_checks) if total_checks > 0 else 100.0
            details = f"{total_violations} values outside bounds ({pct_in_bounds:.1f}% within bounds)"

        return ValidationResult(
            passed=passed,
            total_checks=total_checks,
            failed_checks=total_violations,
            details=details,
            failures=failures,
            metadata={
                "row_count": len(rows),
                "bounded_columns": len(bounded_columns),
                "total_violations": total_violations,
            },
        )

    def _get_bounded_columns(
        self,
        schema_definition: Dict[str, Any],
        columns: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Extract columns with bounds definitions.

        Args:
            schema_definition: Schema definition JSON.
            columns: Available columns in the data.

        Returns:
            Dictionary mapping column name to bounds config.
        """
        if not schema_definition:
            return {}

        bounded: Dict[str, Dict[str, Any]] = {}
        column_defs = schema_definition.get("columns", [])

        for col_def in column_defs:
            col_name = col_def.get("name", "")
            if col_name not in columns:
                continue

            col_type = col_def.get("type", "").lower()
            min_val = col_def.get("min")
            max_val = col_def.get("max")

            if min_val is not None or max_val is not None:
                bounded[col_name] = {
                    "type": col_type,
                    "min": min_val,
                    "max": max_val,
                }

        return bounded

    def _check_bounds(
        self,
        rows: List[Dict[str, Any]],
        col_name: str,
        bounds: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Check bounds for a specific column.

        Args:
            rows: Data rows.
            col_name: Column name to check.
            bounds: Bounds configuration with min/max.

        Returns:
            Dictionary with bounds check statistics.
        """
        col_type = bounds.get("type", "")
        min_val = bounds.get("min")
        max_val = bounds.get("max")

        checked_count = 0
        below_min = 0
        above_max = 0
        sample_violations: List[Dict[str, Any]] = []

        for row_idx, row in enumerate(rows):
            value = row.get(col_name)
            if value is None:
                continue

            checked_count += 1
            parsed_value = self._parse_value(value, col_type)

            if parsed_value is None:
                continue

            is_below = False
            is_above = False

            if min_val is not None:
                parsed_min = self._parse_value(min_val, col_type)
                if parsed_min is not None and parsed_value < parsed_min:
                    is_below = True
                    below_min += 1

            if max_val is not None:
                parsed_max = self._parse_value(max_val, col_type)
                if parsed_max is not None and parsed_value > parsed_max:
                    is_above = True
                    above_max += 1

            if (is_below or is_above) and len(sample_violations) < 10:
                sample_violations.append({
                    "row": row_idx + 1,
                    "value": str(value),
                    "below_min": is_below,
                    "above_max": is_above,
                })

        return {
            "checked_count": checked_count,
            "violation_count": below_min + above_max,
            "below_min": below_min,
            "above_max": above_max,
            "sample_violations": sample_violations,
        }

    def _parse_value(
        self,
        value: Any,
        col_type: str,
    ) -> Optional[Union[int, float, date, datetime]]:
        """Parse a value for comparison.

        Args:
            value: The value to parse.
            col_type: Expected column type.

        Returns:
            Parsed value suitable for comparison, or None if unparseable.
        """
        if value is None:
            return None

        try:
            if col_type in ("integer", "int"):
                return int(value)

            if col_type in ("float", "number", "decimal"):
                return float(value)

            if col_type == "date":
                if isinstance(value, date):
                    return value
                if isinstance(value, datetime):
                    return value.date()
                if isinstance(value, str):
                    return datetime.strptime(value[:10], "%Y-%m-%d").date()

            if col_type == "datetime":
                if isinstance(value, datetime):
                    return value
                if isinstance(value, str):
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))

            # Default: try numeric
            if isinstance(value, (int, float)):
                return value
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        except (ValueError, TypeError):
            return None
