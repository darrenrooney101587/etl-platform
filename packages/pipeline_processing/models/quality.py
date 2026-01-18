"""Data quality result models and scoring structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MetricResult:
    """Result for a single quality dimension (schema, format, completeness, etc.)."""

    passed: bool
    details: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: Dict[str, Any] = {
            "passed": self.passed,
            "details": self.details,
        }
        result.update(self.metadata)
        return result


@dataclass
class DataQualityMetrics:
    """Container for all quality dimension results.

    Required keys per contract:
    - schemaValidation
    - formatParsing
    - completeness
    - boundsRange
    - uniqueness
    """

    schema_validation: MetricResult = field(
        default_factory=lambda: MetricResult(passed=True, details="Not evaluated")
    )
    format_parsing: MetricResult = field(
        default_factory=lambda: MetricResult(passed=True, details="Not evaluated")
    )
    completeness: MetricResult = field(
        default_factory=lambda: MetricResult(passed=True, details="Not evaluated")
    )
    bounds_range: MetricResult = field(
        default_factory=lambda: MetricResult(passed=True, details="Not evaluated")
    )
    uniqueness: MetricResult = field(
        default_factory=lambda: MetricResult(passed=True, details="Not evaluated")
    )

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """Convert to dictionary matching the JSON contract."""
        return {
            "schemaValidation": self.schema_validation.to_dict(),
            "formatParsing": self.format_parsing.to_dict(),
            "completeness": self.completeness.to_dict(),
            "boundsRange": self.bounds_range.to_dict(),
            "uniqueness": self.uniqueness.to_dict(),
        }


@dataclass
class DataQualityDeductions:
    """Deduction points for each quality dimension.

    Max deductions per contract:
    - schema: 40
    - format: 35
    - completeness: 20
    - bounds: 15
    - uniqueness: 10
    """

    schema: float = 0.0
    format: float = 0.0
    completeness: float = 0.0
    bounds: float = 0.0
    uniqueness: float = 0.0

    MAX_SCHEMA: float = 40.0
    MAX_FORMAT: float = 35.0
    MAX_COMPLETENESS: float = 20.0
    MAX_BOUNDS: float = 15.0
    MAX_UNIQUENESS: float = 10.0

    def total(self) -> float:
        """Return the sum of all deductions."""
        return self.schema + self.format + self.completeness + self.bounds + self.uniqueness

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary matching the JSON contract."""
        return {
            "schema": round(self.schema, 2),
            "format": round(self.format, 2),
            "completeness": round(self.completeness, 2),
            "bounds": round(self.bounds, 2),
            "uniqueness": round(self.uniqueness, 2),
        }


@dataclass
class SampleData:
    """Sample rows for profiling payload."""

    columns: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "columns": self.columns,
            "rows": self.rows,
        }


@dataclass
class ProfilePayload:
    """Data profiling payload for analyst exploration.

    Contains statistical summaries, distributions, and sample data.
    Payload sizes are capped per contract:
    - sample rows: 25-50
    - distribution examples: 10-25 items
    """

    # Allow either list or dict forms; canonical internal format is list for frontend
    statistical_summary: Any = field(default_factory=list)
    completeness_overview: Dict[str, Any] = field(default_factory=dict)
    type_format_issues: List[Dict[str, Any]] = field(default_factory=list)
    uniqueness_overview: Dict[str, Any] = field(default_factory=dict)
    # value_distributions may be produced as a list of {column,histogram} or dict mapping column->hist
    value_distributions: Any = field(default_factory=list)
    bounds_anomalies: List[Dict[str, Any]] = field(default_factory=list)
    sample_data: Optional[SampleData] = None

    MAX_SAMPLE_ROWS: int = 50
    MAX_DISTRIBUTION_ITEMS: int = 25
    MAX_ANOMALY_EXAMPLES: int = 25

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary matching the JSON contract."""
        # Normalize statistical summary to list form
        stat = self.statistical_summary
        if isinstance(stat, dict):
            # convert dict-of-columns to list
            try:
                stat_list = [v for _, v in stat.items()]
            except Exception:
                stat_list = []
        else:
            stat_list = stat or []

        # Normalize value distributions to list of {column, histogram}
        vd = self.value_distributions
        vd_list: List[Dict[str, Any]]
        if isinstance(vd, dict):
            vd_list = [
                {"column": k, "histogram": (v[: self.MAX_DISTRIBUTION_ITEMS] if isinstance(v, list) else [])}
                for k, v in vd.items()
            ]
        elif isinstance(vd, list):
            # Ensure each histogram array is trimmed
            vd_list = []
            for item in vd:
                if not isinstance(item, dict):
                    continue
                col = item.get("column")
                hist = item.get("histogram") or item.get("distribution") or []
                if isinstance(hist, list):
                    hist = hist[: self.MAX_DISTRIBUTION_ITEMS]
                else:
                    hist = []
                vd_list.append({"column": col, "histogram": hist})
        else:
            vd_list = []

        result: Dict[str, Any] = {
            "statisticalSummary": stat_list,
            "completenessOverview": self.completeness_overview,
            "typeFormatIssues": self.type_format_issues[: self.MAX_ANOMALY_EXAMPLES],
            "uniquenessOverview": self.uniqueness_overview,
            "valueDistributions": vd_list,
            "boundsAnomalies": self.bounds_anomalies[: self.MAX_ANOMALY_EXAMPLES],
        }
        if self.sample_data:
            result["sampleData"] = {
                "columns": self.sample_data.columns,
                "rows": self.sample_data.rows[:self.MAX_SAMPLE_ROWS],
            }
        return result


@dataclass
class DataQualityResult:
    """Complete data quality result for a file run.

    This is the main output structure from the data quality processor.
    """

    score: int
    passed: bool
    metrics: DataQualityMetrics
    deductions: DataQualityDeductions
    profile: Optional[ProfilePayload] = None
    failed_validation_message: Optional[str] = None
    failed_validation_rules: Optional[List[Dict[str, Any]]] = None

    @classmethod
    def compute_score(cls, deductions: DataQualityDeductions) -> int:
        """Compute final score from deductions.

        Score = clamp(round(100 - sum(deductions)), 0, 100)
        """
        raw_score = 100.0 - deductions.total()
        return max(0, min(100, round(raw_score)))

    @classmethod
    def is_passed(cls, score: int) -> bool:
        """Determine if the quality check passed.

        Pass threshold is score >= 80.
        """
        return score >= 80

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the DataQualityResult to a JSON-serializable dict.

        Keeps keys stable for dry-run output and debugging.
        """
        return {
            "score": self.score,
            "passed": self.passed,
            "metrics": self.metrics.to_dict(),
            "deductions": self.deductions.to_dict(),
            "profile": self.profile.to_dict() if self.profile is not None else None,
            "failed_validation_message": self.failed_validation_message,
            "failed_validation_rules": self.failed_validation_rules,
        }
