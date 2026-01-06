"""Uniqueness validation for data files.

Validates that declared unique keys have unique values.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Tuple

from file_processing.validators.base import BaseValidator, ValidationResult

logger = logging.getLogger(__name__)


class UniquenessValidator(BaseValidator):
    """Validator for uniqueness constraints.

    Checks that declared unique key columns have unique values across all rows.
    """

    @property
    def validator_name(self) -> str:
        """Return the validator name."""
        return "uniqueness"

    def validate(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        schema_definition: Dict[str, Any],
    ) -> ValidationResult:
        """Validate uniqueness of declared unique keys.

        Schema definition expected format:
        {
            "unique_keys": ["id"],  // Single column unique key
            // or
            "unique_keys": [["col1", "col2"]],  // Composite unique key
            // or
            "columns": [
                {"name": "id", "unique": true},
                {"name": "pk_col", "primary_key": true},
                ...
            ]
        }

        Args:
            rows: Parsed data rows.
            columns: Column names from the file.
            schema_definition: Schema definition JSON.

        Returns:
            ValidationResult with uniqueness details.
        """
        if not rows:
            return ValidationResult(
                passed=True,
                details="No rows to validate",
                metadata={"row_count": 0},
            )

        unique_keys = self._get_unique_keys(schema_definition, columns)

        if not unique_keys:
            return ValidationResult(
                passed=True,
                details="No unique keys defined; skipping uniqueness validation",
                metadata={"row_count": len(rows)},
            )

        failures: List[Dict[str, Any]] = []
        total_checks = 0
        total_duplicates = 0

        for key_cols in unique_keys:
            result = self._check_uniqueness(rows, key_cols)
            total_checks += len(rows)
            total_duplicates += result["duplicate_count"]

            if result["duplicate_count"] > 0:
                failures.append({
                    "check": "uniqueness",
                    "columns": key_cols,
                    "unique_count": result["unique_count"],
                    "duplicate_count": result["duplicate_count"],
                    "uniqueness_ratio": result["uniqueness_ratio"],
                    "sample_duplicates": result["sample_duplicates"][:10],
                    "message": f"Key {key_cols} has {result['duplicate_count']} duplicate entries ({result['uniqueness_ratio']*100:.1f}% unique)",
                })

        passed = total_duplicates == 0

        if passed:
            details = f"All {len(unique_keys)} unique key constraints satisfied across {len(rows)} rows"
        else:
            avg_ratio = 1.0 - (total_duplicates / total_checks) if total_checks > 0 else 1.0
            details = f"Uniqueness ratio: {avg_ratio*100:.1f}% ({total_duplicates} duplicate key values)"

        return ValidationResult(
            passed=passed,
            total_checks=total_checks,
            failed_checks=total_duplicates,
            details=details,
            failures=failures,
            metadata={
                "row_count": len(rows),
                "unique_keys_checked": len(unique_keys),
                "total_duplicates": total_duplicates,
            },
        )

    def _get_unique_keys(
        self,
        schema_definition: Dict[str, Any],
        columns: List[str],
    ) -> List[List[str]]:
        """Extract unique key definitions from schema.

        Args:
            schema_definition: Schema definition JSON.
            columns: Available columns in the data.

        Returns:
            List of unique key column lists.
        """
        if not schema_definition:
            return []

        unique_keys: List[List[str]] = []

        # Check for explicit unique_keys definition
        if "unique_keys" in schema_definition:
            for key in schema_definition["unique_keys"]:
                if isinstance(key, str):
                    if key in columns:
                        unique_keys.append([key])
                elif isinstance(key, list):
                    if all(col in columns for col in key):
                        unique_keys.append(key)

        # Check column-level unique flags
        column_defs = schema_definition.get("columns", [])
        for col_def in column_defs:
            col_name = col_def.get("name", "")
            # Check both strict 'unique' constraint and 'primary_key' definition
            is_unique = col_def.get("unique", False)
            is_pk = col_def.get("primary_key", False) or col_def.get("is_primary_key", False)

            if (is_unique or is_pk) and col_name in columns:
                # Avoid duplicates
                if [col_name] not in unique_keys:
                    unique_keys.append([col_name])

        return unique_keys

    def _check_uniqueness(
        self,
        rows: List[Dict[str, Any]],
        key_cols: List[str],
    ) -> Dict[str, Any]:
        """Check uniqueness for a specific key.

        Args:
            rows: Data rows.
            key_cols: Columns that form the unique key.

        Returns:
            Dictionary with uniqueness statistics.
        """
        # Build composite keys
        keys: List[Tuple[Any, ...]] = []
        for row in rows:
            key = tuple(row.get(col) for col in key_cols)
            keys.append(key)

        # Count occurrences
        counter = Counter(keys)
        unique_count = len(counter)
        total_count = len(keys)

        # Find duplicates
        duplicates = [(k, c) for k, c in counter.items() if c > 1]
        duplicate_count = sum(c - 1 for _, c in duplicates)

        # Sample of duplicate values
        sample_duplicates: List[Dict[str, Any]] = []
        for key_val, count in duplicates[:10]:
            sample_duplicates.append({
                "key_value": dict(zip(key_cols, key_val)),
                "occurrences": count,
            })

        uniqueness_ratio = unique_count / total_count if total_count > 0 else 1.0

        return {
            "unique_count": unique_count,
            "total_count": total_count,
            "duplicate_count": duplicate_count,
            "uniqueness_ratio": round(uniqueness_ratio, 4),
            "sample_duplicates": sample_duplicates,
        }
