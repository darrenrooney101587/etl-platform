"""Unit tests for data quality validators."""
import unittest
from typing import Any, Dict, List

from file_processing.validators import (
    BoundsValidator,
    CompletenessValidator,
    SchemaValidator,
    UniquenessValidator,
)


class SchemaValidatorTest(unittest.TestCase):
    """Tests for SchemaValidator."""

    def test_validate_with_no_schema(self) -> None:
        """Test validation passes when no schema is defined."""
        validator = SchemaValidator()
        rows = [{"a": 1, "b": 2}]
        columns = ["a", "b"]

        result = validator.validate(rows, columns, {})

        self.assertTrue(result.passed)

    def test_validate_required_columns_present(self) -> None:
        """Test validation passes when all required columns are present."""
        validator = SchemaValidator()
        rows = [{"id": 1, "name": "test"}]
        columns = ["id", "name"]
        schema = {
            "columns": [
                {"name": "id", "required": True},
                {"name": "name", "required": True},
            ]
        }

        result = validator.validate(rows, columns, schema)

        self.assertTrue(result.passed)

    def test_validate_required_column_missing(self) -> None:
        """Test validation fails when required column is missing."""
        validator = SchemaValidator()
        rows = [{"id": 1}]
        columns = ["id"]
        schema = {
            "columns": [
                {"name": "id", "required": True},
                {"name": "name", "required": True},
            ]
        }

        result = validator.validate(rows, columns, schema)

        self.assertFalse(result.passed)
        self.assertGreater(result.failed_checks, 0)


class CompletenessValidatorTest(unittest.TestCase):
    """Tests for CompletenessValidator."""

    def test_validate_complete_data(self) -> None:
        """Test validation passes with complete data."""
        validator = CompletenessValidator()
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        columns = ["id", "name"]
        schema = {
            "columns": [
                {"name": "id", "required": True, "nullable": False},
                {"name": "name", "required": True, "nullable": False},
            ]
        }

        result = validator.validate(rows, columns, schema)

        self.assertTrue(result.passed)

    def test_validate_with_nulls(self) -> None:
        """Test validation fails with null values in required columns."""
        validator = CompletenessValidator()
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": None},
        ]
        columns = ["id", "name"]
        schema = {
            "columns": [
                {"name": "id", "required": True, "nullable": False},
                {"name": "name", "required": True, "nullable": False},
            ]
        }

        result = validator.validate(rows, columns, schema)

        self.assertFalse(result.passed)
        self.assertEqual(result.failed_checks, 1)

    def test_validate_empty_string_as_null(self) -> None:
        """Test that empty strings are treated as null."""
        validator = CompletenessValidator()
        rows = [{"id": 1, "name": "  "}]
        columns = ["id", "name"]
        schema = {
            "columns": [
                {"name": "name", "required": True, "nullable": False},
            ]
        }

        result = validator.validate(rows, columns, schema)

        self.assertFalse(result.passed)


class UniquenessValidatorTest(unittest.TestCase):
    """Tests for UniquenessValidator."""

    def test_validate_unique_values(self) -> None:
        """Test validation passes with unique values."""
        validator = UniquenessValidator()
        rows = [{"id": 1}, {"id": 2}, {"id": 3}]
        columns = ["id"]
        schema = {"unique_keys": ["id"]}

        result = validator.validate(rows, columns, schema)

        self.assertTrue(result.passed)

    def test_validate_duplicate_values(self) -> None:
        """Test validation fails with duplicate values."""
        validator = UniquenessValidator()
        rows = [{"id": 1}, {"id": 2}, {"id": 1}]
        columns = ["id"]
        schema = {"unique_keys": ["id"]}

        result = validator.validate(rows, columns, schema)

        self.assertFalse(result.passed)
        self.assertEqual(result.failed_checks, 1)  # One duplicate

    def test_validate_composite_key(self) -> None:
        """Test validation with composite unique key."""
        validator = UniquenessValidator()
        rows = [
            {"a": 1, "b": 1},
            {"a": 1, "b": 2},
            {"a": 1, "b": 1},  # Duplicate
        ]
        columns = ["a", "b"]
        schema = {"unique_keys": [["a", "b"]]}

        result = validator.validate(rows, columns, schema)

        self.assertFalse(result.passed)


class BoundsValidatorTest(unittest.TestCase):
    """Tests for BoundsValidator."""

    def test_validate_within_bounds(self) -> None:
        """Test validation passes when values are within bounds."""
        validator = BoundsValidator()
        rows = [{"age": 25}, {"age": 30}, {"age": 35}]
        columns = ["age"]
        schema = {
            "columns": [
                {"name": "age", "type": "integer", "min": 0, "max": 150},
            ]
        }

        result = validator.validate(rows, columns, schema)

        self.assertTrue(result.passed)

    def test_validate_below_min(self) -> None:
        """Test validation fails when value is below minimum."""
        validator = BoundsValidator()
        rows = [{"age": -5}]
        columns = ["age"]
        schema = {
            "columns": [
                {"name": "age", "type": "integer", "min": 0},
            ]
        }

        result = validator.validate(rows, columns, schema)

        self.assertFalse(result.passed)

    def test_validate_above_max(self) -> None:
        """Test validation fails when value is above maximum."""
        validator = BoundsValidator()
        rows = [{"price": 1000}]
        columns = ["price"]
        schema = {
            "columns": [
                {"name": "price", "type": "float", "max": 100.0},
            ]
        }

        result = validator.validate(rows, columns, schema)

        self.assertFalse(result.passed)

    def test_validate_no_bounds(self) -> None:
        """Test validation passes when no bounds are defined."""
        validator = BoundsValidator()
        rows = [{"value": 999999}]
        columns = ["value"]
        schema = {"columns": [{"name": "value", "type": "integer"}]}

        result = validator.validate(rows, columns, schema)

        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
