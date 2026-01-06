"""Dataclass mirrors for the reporting.monitoring_* tables.

These are pure Python dataclasses that represent rows in the shared Postgres
database. They do NOT use Django ORM - this package connects directly via psycopg2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@dataclass
class MonitoringFileSchemaDefinition:
    """Mirror of reporting.monitoring_file_schema_definition table.

    The schema definition contains a JSON definition that describes
    expected columns, types, required fields, unique keys, and bounds.
    """

    id: int
    name: str
    description: Optional[str] = None
    definition: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class MonitoringFile:
    """Mirror of reporting.monitoring_file table.

    Represents a monitored file configuration for a specific agency.
    """

    id: int
    file_name: str
    agency_slug: str
    latest_data_quality_score: Optional[int] = None
    schema_definition_id: Optional[int] = None
    schema_definition: Optional[MonitoringFileSchemaDefinition] = None
    is_suppressed: bool = False


@dataclass
class MonitoringFileRun:
    """Mirror of reporting.monitoring_file_run table.

    Represents a single hourly processing run for a monitoring file.
    Uniqueness constraint: (monitoring_file_id, run_date, run_hour).
    """

    id: int
    monitoring_file_id: int
    run_date: date
    run_hour: int
    agency_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    file_last_modified: Optional[datetime] = None
    file_range_lower_limit: Optional[datetime] = None
    file_size: Optional[int] = None


@dataclass
class MonitoringFileDataQuality:
    """Mirror of reporting.monitoring_file_data_quality table.

    Stores computed data quality score and dimension breakdown for a run.
    One-to-one relationship with MonitoringFileRun.
    """

    id: int
    monitoring_file_run_id: int
    score: int
    passed: bool
    monitoring_file_id: Optional[int] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    deductions: Dict[str, float] = field(default_factory=dict)
    failed_validation_message: Optional[str] = None
    failed_validation_rules: Optional[List[Dict[str, Any]]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class MonitoringFileFailedValidation:
    """Mirror of reporting.monitoring_file_failed_validation table.

    Stores rule-level failure details for a run.
    """

    id: int
    monitoring_file_id: int
    monitoring_file_run_id: int
    rule_name: str = ""
    rule_type: str = ""
    rule_path: str = ""
    validated_field_names: str = ""
    validated_values: str = ""
    rule_parameters: str = ""
    validated_at: Optional[datetime] = None
    validated_message: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class MonitoringFileDataProfile:
    """Mirror of reporting.monitoring_file_data_profile table.

    Stores data profiling payload for analyst exploration.
    One-to-one relationship with MonitoringFileRun.
    """

    id: int
    monitoring_file_run_id: int
    monitoring_file_id: Optional[int] = None
    statistical_summary: List[Any] = field(default_factory=list)
    completeness_overview: List[Any] = field(default_factory=list)
    type_format_issues: List[Any] = field(default_factory=list)
    uniqueness_overview: List[Any] = field(default_factory=list)
    value_distributions: List[Any] = field(default_factory=list)
    bounds_anomalies: List[Any] = field(default_factory=list)
    sample_data: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
