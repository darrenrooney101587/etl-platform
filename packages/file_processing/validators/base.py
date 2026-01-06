"""Base validator interface and common types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ValidationResult:
    """Result from a validation check.

    Attributes:
        passed: Whether all checks passed.
        total_checks: Total number of individual checks performed.
        failed_checks: Number of checks that failed.
        details: Human-readable summary of the result.
        failures: List of specific failure details.
        metadata: Additional validation metadata.
    """

    passed: bool
    total_checks: int = 0
    failed_checks: int = 0
    details: str = ""
    failures: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def failure_ratio(self) -> float:
        """Return the ratio of failed checks to total checks.

        Returns 0.0 if no checks were performed.
        """
        if self.total_checks == 0:
            return 0.0
        return self.failed_checks / self.total_checks


class BaseValidator(ABC):
    """Abstract base class for data quality validators."""

    @property
    @abstractmethod
    def validator_name(self) -> str:
        """Return the name of this validator."""
        ...

    @abstractmethod
    def validate(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        schema_definition: Dict[str, Any],
    ) -> ValidationResult:
        """Perform validation on the parsed data.

        Args:
            rows: List of parsed data rows as dictionaries.
            columns: List of column names from the file.
            schema_definition: Schema definition from MonitoringFileSchemaDefinition.

        Returns:
            ValidationResult with pass/fail status and details.
        """
        ...
