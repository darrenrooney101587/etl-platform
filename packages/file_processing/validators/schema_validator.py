"""Schema validation for data files.

Validates that data matches the expected schema definition including
column presence, data types, and required fields.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Set

from file_processing.validators.base import BaseValidator, ValidationResult

logger = logging.getLogger(__name__)


class SchemaValidator(BaseValidator):
    """Validator for schema compliance.

    Checks:
    - Required columns are present
    - Column data types match expected types
    - No unexpected columns (optional, configurable)
    """

    @property
    def validator_name(self) -> str:
        """Return the validator name."""
        return "schema"

    def validate(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        schema_definition: Dict[str, Any],
    ) -> ValidationResult:
        """Validate data against the schema definition.

        Schema definition expected format:
        {
            "columns": [
                {"name": "col1", "type": "string", "required": true},
                {"name": "col2", "type": "integer", "required": false},
                ...
            ],
            "strict": false  // if true, reject unexpected columns
        }

        Args:
            rows: Parsed data rows.
            columns: Column names from the file.
            schema_definition: Schema definition JSON.

        Returns:
            ValidationResult with schema compliance details.
        """
        if not schema_definition:
            return ValidationResult(
                passed=True,
                details="No schema definition provided; skipping schema validation",
            )

        expected_columns = schema_definition.get("columns", [])
        if not expected_columns:
            return ValidationResult(
                passed=True,
                details="No columns defined in schema; skipping schema validation",
            )


        # Build mapping from schema names to actual column names
        # This handles case-insensitivity and regex patterns
        column_map = self._build_column_mapping(columns, expected_columns)
        mapped_actual_columns = set(column_map.values())

        failures: List[Dict[str, Any]] = []
        total_checks = 0

        # Check required columns
        for col_def in expected_columns:
            col_name = col_def.get("name", "")
            is_required = col_def.get("required", False)

            if is_required:
                total_checks += 1
                if col_name not in column_map:
                    failures.append({
                        "check": "required_column",
                        "column": col_name,
                        "message": f"Required column '{col_name}' is missing",
                    })


        # Type validation on sample of rows (first 100)
        sample_rows = rows[:100]
        type_failures = self._validate_types(sample_rows, expected_columns, column_map)
        total_checks += len(expected_columns) * min(len(rows), 100)
        failures.extend(type_failures)

        passed = len(failures) == 0

        if passed:
            details = f"All {len(expected_columns)} schema columns validated successfully"
        else:
            details = f"{len(failures)} schema validation failures out of {total_checks} checks"

        return ValidationResult(
            passed=passed,
            total_checks=total_checks,
            failed_checks=len(failures),
            details=details,
            failures=failures[:25],  # Limit failure examples
            metadata={
                "expected_columns": len(expected_columns),
                "actual_columns": len(columns),
            },
        )

    def _build_column_mapping(
        self,
        actual_columns: List[str],
        expected_columns: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        """Map schema column names to actual column names.

        Supports:
        1. Exact match
        2. Case-insensitive match
        3. Regex pattern match (if 'pattern' is defined in schema)

        Args:
            actual_columns: List of column names from the file.
            expected_columns: List of column definitions from schema.

        Returns:
            Dictionary mapping schema_name -> actual_name.
        """
        mapping: Dict[str, str] = {}
        actual_set = set(actual_columns)

        # Helper to find case-insensitive match
        actual_lower_map = {col.lower(): col for col in actual_columns}

        for col_def in expected_columns:
            schema_name = col_def.get("name", "")
            if not schema_name:
                continue

            # 1. Exact match
            if schema_name in actual_set:
                mapping[schema_name] = schema_name
                continue

            # 2. Case-insensitive match
            if schema_name.lower() in actual_lower_map:
                mapping[schema_name] = actual_lower_map[schema_name.lower()]
                continue

            # 3. Regex match
            pattern = col_def.get("pattern")
            if pattern:
                try:
                    regex = re.compile(pattern, re.IGNORECASE)
                    for actual in actual_columns:
                        if regex.match(actual):
                            mapping[schema_name] = actual
                            break
                except re.error:
                    logger.warning("Invalid regex pattern for column %s: %s", schema_name, pattern)

        return mapping

    def _validate_types(
        self,
        rows: List[Dict[str, Any]],
        column_defs: List[Dict[str, Any]],
        column_map: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Validate data types for columns.

        Args:
            rows: Sample rows to validate.
            column_defs: Column definitions with type info.
            column_map: Mapping from schema name to actual column name.

        Returns:
            List of type validation failures.
        """
        failures: List[Dict[str, Any]] = []
        type_error_counts: Dict[str, int] = {}

        for col_def in column_defs:
            schema_name = col_def.get("name", "")
            actual_name = column_map.get(schema_name)

            # Skip if column is missing (handled by required check)
            if not actual_name:
                continue

            expected_type = col_def.get("type", "").lower()

            if not expected_type or expected_type in ("any", "string"):
                continue

            for row_idx, row in enumerate(rows):
                value = row.get(actual_name)
                if value is None:
                    continue  # Null values handled by completeness validator

                if not self._check_type(value, expected_type):
                    key = f"{schema_name}:{expected_type}"
                    type_error_counts[key] = type_error_counts.get(key, 0) + 1

                    # Only record first few examples per column
                    if type_error_counts[key] <= 3:
                        failures.append({
                            "check": "type_mismatch",
                            "column": schema_name,
                            "actual_column": actual_name,
                            "expected_type": expected_type,
                            "actual_value": str(value)[:50],
                            "row": row_idx + 1,
                            "message": f"Column '{actual_name}' expected type '{expected_type}', got '{type(value).__name__}'",
                        })

        return failures

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if a value matches the expected type.

        Args:
            value: The value to check.
            expected_type: Expected type name (string, integer, float, boolean, date, datetime).

        Returns:
            True if the value matches the expected type.
        """
        if expected_type in ("string", "str", "text"):
            return isinstance(value, str)

        if expected_type in ("integer", "int"):
            if isinstance(value, bool):
                return False
            if isinstance(value, int):
                return True
            if isinstance(value, str):
                try:
                    int(value)
                    return True
                except ValueError:
                    return False
            return False

        if expected_type in ("float", "number", "decimal"):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return True
            if isinstance(value, str):
                try:
                    float(value)
                    return True
                except ValueError:
                    return False
            return False

        if expected_type in ("boolean", "bool"):
            if isinstance(value, bool):
                return True
            if isinstance(value, str):
                return value.lower() in ("true", "false", "1", "0", "yes", "no")
            return False

        if expected_type in ("date", "datetime"):
            from datetime import date, datetime
            if isinstance(value, (date, datetime)):
                return True
            # Allow ISO format strings
            if isinstance(value, str):
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return True
                except ValueError:
                    pass
            return False

        # Unknown type - allow by default
        return True
