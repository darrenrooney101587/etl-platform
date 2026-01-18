"""DAG file validator.

Validates DAG files for common issues before publishing to S3.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


class DAGValidationError(Exception):
    """Raised when DAG validation fails."""

    pass


class DAGValidator:
    """Validates Airflow DAG files."""

    def __init__(self, package_name: str):
        """Initialize the validator.

        Args:
            package_name: Name of the package (for DAG ID prefix validation).
        """
        self.package_name = package_name

    def validate_file(self, dag_file: Path) -> None:
        """Validate a DAG file.

        Args:
            dag_file: Path to the DAG file.

        Raises:
            DAGValidationError: If validation fails.
            FileNotFoundError: If file doesn't exist.
        """
        if not dag_file.exists():
            raise FileNotFoundError(f"DAG file not found: {dag_file}")

        logger.info("Validating DAG file: %s", dag_file)

        # Check Python syntax
        self._validate_syntax(dag_file)

        # Check for required Airflow imports
        self._validate_imports(dag_file)

        # Check DAG ID convention (should start with package name)
        dag_id = self._extract_dag_id(dag_file)
        if dag_id:
            self._validate_dag_id(dag_id)

        logger.info("DAG file validation passed: %s", dag_file)

    def _validate_syntax(self, dag_file: Path) -> None:
        """Validate Python syntax.

        Args:
            dag_file: Path to the DAG file.

        Raises:
            DAGValidationError: If syntax is invalid.
        """
        try:
            with open(dag_file, "r") as f:
                code = f.read()
            ast.parse(code)
        except SyntaxError as e:
            raise DAGValidationError(
                f"Syntax error in {dag_file}: {e.msg} at line {e.lineno}"
            ) from e

    def _validate_imports(self, dag_file: Path) -> None:
        """Validate that required Airflow imports are present.

        Args:
            dag_file: Path to the DAG file.

        Raises:
            DAGValidationError: If required imports are missing.
        """
        with open(dag_file, "r") as f:
            content = f.read()

        # Check for basic Airflow imports
        if "from airflow" not in content and "import airflow" not in content:
            raise DAGValidationError(
                f"DAG file {dag_file} does not import from airflow"
            )

        # Check for DAG definition
        if "DAG" not in content and "dag=" not in content.lower():
            logger.warning(
                "DAG file %s may be missing a DAG definition (no 'DAG' or 'dag=' found)",
                dag_file,
            )

    def _extract_dag_id(self, dag_file: Path) -> Optional[str]:
        """Extract the DAG ID from a DAG file.

        Args:
            dag_file: Path to the DAG file.

        Returns:
            DAG ID if found, None otherwise.
        """
        try:
            with open(dag_file, "r") as f:
                tree = ast.parse(f.read())

            # Look for dag_id in DAG() constructor calls
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if hasattr(node.func, "id") and node.func.id == "DAG":
                        for keyword in node.keywords:
                            if keyword.arg == "dag_id":
                                if isinstance(keyword.value, ast.Constant):
                                    return keyword.value.value

            # Also check for @dag decorator
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Call):
                            if hasattr(decorator.func, "id") and decorator.func.id == "dag":
                                for keyword in decorator.keywords:
                                    if keyword.arg == "dag_id":
                                        if isinstance(keyword.value, ast.Constant):
                                            return keyword.value.value
                                # If no dag_id specified, function name is used
                                return node.name

        except Exception as e:
            logger.warning("Could not extract DAG ID from %s: %s", dag_file, e)

        return None

    def _validate_dag_id(self, dag_id: str) -> None:
        """Validate that DAG ID follows naming convention.

        Args:
            dag_id: The DAG ID to validate.

        Raises:
            DAGValidationError: If DAG ID is invalid.
        """
        # DAG ID should start with package name
        if not dag_id.startswith(f"{self.package_name}_"):
            logger.warning(
                "DAG ID '%s' does not start with package name '%s'. "
                "Convention is '<package>_<dag_name>' for global uniqueness.",
                dag_id,
                self.package_name,
            )

        # DAG ID should not contain spaces
        if " " in dag_id:
            raise DAGValidationError(
                f"DAG ID '{dag_id}' contains spaces. Use underscores instead."
            )

        # DAG ID should be alphanumeric (plus underscore, hyphen, dot)
        allowed_chars = set("abcdefghijklmnopqrstuvwxyz0123456789_-.")
        if not all(c in allowed_chars for c in dag_id.lower()):
            raise DAGValidationError(
                f"DAG ID '{dag_id}' contains invalid characters. "
                "Only alphanumeric, underscore, hyphen, and dot are allowed."
            )
