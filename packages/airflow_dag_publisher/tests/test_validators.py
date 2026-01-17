"""Tests for DAG validator."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile

from airflow_dag_publisher.validators import DAGValidator, DAGValidationError


class TestDAGValidator(unittest.TestCase):
    """Test DAGValidator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.validator = DAGValidator(package_name="test_package")

    def test_validate_syntax_error(self):
        """Test that syntax errors are caught."""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def invalid syntax")
            f.flush()
            dag_file = Path(f.name)

        try:
            with self.assertRaises(DAGValidationError) as cm:
                self.validator.validate_file(dag_file)
            self.assertIn("Syntax error", str(cm.exception))
        finally:
            dag_file.unlink()

    def test_validate_missing_airflow_import(self):
        """Test that missing Airflow imports are caught."""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# Valid Python but no Airflow imports\nprint('hello')\n")
            f.flush()
            dag_file = Path(f.name)

        try:
            with self.assertRaises(DAGValidationError) as cm:
                self.validator.validate_file(dag_file)
            self.assertIn("does not import from airflow", str(cm.exception))
        finally:
            dag_file.unlink()

    def test_validate_valid_dag(self):
        """Test that valid DAGs pass validation."""
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
from airflow import DAG
from datetime import datetime

with DAG(
    dag_id="test_package_example",
    start_date=datetime(2024, 1, 1),
) as dag:
    pass
"""
            )
            f.flush()
            dag_file = Path(f.name)

        try:
            # Should not raise
            self.validator.validate_file(dag_file)
        finally:
            dag_file.unlink()

    def test_dag_id_with_spaces(self):
        """Test that DAG IDs with spaces are rejected."""
        with self.assertRaises(DAGValidationError) as cm:
            self.validator._validate_dag_id("test package example")
        self.assertIn("contains spaces", str(cm.exception))

    def test_dag_id_with_invalid_chars(self):
        """Test that DAG IDs with invalid characters are rejected."""
        with self.assertRaises(DAGValidationError) as cm:
            self.validator._validate_dag_id("test_package@example!")
        self.assertIn("invalid characters", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
