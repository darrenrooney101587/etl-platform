"""Data models for the file processing package.

These are pure Python dataclasses that mirror the shared Postgres reporting tables.
They are NOT Django ORM models - this package does not use Django.
"""
from __future__ import annotations

from file_processing.models.monitoring import (
    MonitoringFile,
    MonitoringFileDataProfile,
    MonitoringFileDataQuality,
    MonitoringFileFailedValidation,
    MonitoringFileRun,
    MonitoringFileSchemaDefinition,
)
from file_processing.models.quality import (
    DataQualityDeductions,
    DataQualityMetrics,
    DataQualityResult,
    ProfilePayload,
)
from file_processing.models.events import S3Event

__all__ = [
    "DataQualityDeductions",
    "DataQualityMetrics",
    "DataQualityResult",
    "MonitoringFile",
    "MonitoringFileDataProfile",
    "MonitoringFileDataQuality",
    "MonitoringFileFailedValidation",
    "MonitoringFileRun",
    "MonitoringFileSchemaDefinition",
    "ProfilePayload",
    "S3Event",
]
