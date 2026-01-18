"""Completeness validation for data files.

Validates that required fields have non-null values.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from pipeline_processing.validators.base import BaseValidator, ValidationResult

logger = logging.getLogger(__name__)


class CompletenessValidator(BaseValidator):
    """Validator for data completeness.

    Checks that required fields have non-null, non-empty values.
    """

    @property
    def validator_name(self) -> str:
        """Return the validator name."""
        return "completeness"

    def validate(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        schema_definition: Dict[str, Any],
    ) -> ValidationResult:
        """Validate completeness of required fields.

        Schema definition expected format:
        {
            "columns": [
                {"name": "col1", "required": true, "nullable": false},
                ...
            ]
        }

        Args:
            rows: Parsed data rows.
            columns: Column names from the file.
            schema_definition: Schema definition JSON.

        Returns:
            ValidationResult with completeness details.
        """
        if not rows:
            return ValidationResult(
                passed=True,
                details="No rows to validate",
                metadata={"row_count": 0},
            )

        required_columns = self._get_required_columns(schema_definition, columns)

        if not required_columns:
            return ValidationResult(
                passed=True,
                details="No required columns defined; all columns considered optional",
                metadata={"row_count": len(rows)},
            )

        total_checks = len(rows) * len(required_columns)
        null_counts: Dict[str, int] = {col: 0 for col in required_columns}
        sample_nulls: Dict[str, List[int]] = {col: [] for col in required_columns}

        for row_idx, row in enumerate(rows):
            for col in required_columns:
                value = row.get(col)
                if self._is_null_or_empty(value):
                    null_counts[col] += 1
                    if len(sample_nulls[col]) < 5:
                        sample_nulls[col].append(row_idx + 1)

        total_nulls = sum(null_counts.values())
        failed_columns = [col for col, count in null_counts.items() if count > 0]

        completeness_pct = 100.0 * (1 - total_nulls / total_checks) if total_checks > 0 else 100.0

        failures: List[Dict[str, Any]] = []
        for col in failed_columns:
            count = null_counts[col]
            pct = 100.0 * count / len(rows)
            failures.append({
                "check": "null_required_field",
                "column": col,
                "null_count": count,
                "null_percent": round(pct, 2),
                "sample_rows": sample_nulls[col],
                "message": f"Column '{col}' has {count} null values ({pct:.1f}%)",
            })

        passed = total_nulls == 0

        if passed:
            details = f"All {len(required_columns)} required columns are complete across {len(rows)} rows"
        else:
            details = f"{round(100 - completeness_pct, 1)}% of required field values are null/empty"

        return ValidationResult(
            passed=passed,
            total_checks=total_checks,
            failed_checks=total_nulls,
            details=details,
            failures=failures,
            metadata={
                "row_count": len(rows),
                "required_columns": len(required_columns),
                "completeness_percent": round(completeness_pct, 2),
                "columns_with_nulls": len(failed_columns),
            },
        )

    def _get_required_columns(
        self,
        schema_definition: Dict[str, Any],
        columns: List[str],
    ) -> List[str]:
        """Extract list of required, non-nullable columns.

        Args:
            schema_definition: Schema definition JSON.
            columns: Available columns in the data.

        Returns:
            List of required column names.
        """
        if not schema_definition:
            return []

        column_defs = schema_definition.get("columns", [])
        required: List[str] = []

        for col_def in column_defs:
            col_name = col_def.get("name", "")
            is_required = col_def.get("required", False)
            # is_nullable = col_def.get("nullable", True) # Ignore nullable default for now

            # Column is required if explicitly marked required
            if is_required and col_name in columns:
                required.append(col_name)

        return required

    def _is_null_or_empty(self, value: Any) -> bool:
        """Check if a value is null or empty.

        Args:
            value: The value to check.

        Returns:
            True if the value is None, empty string, or whitespace-only.
        """
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        return False
