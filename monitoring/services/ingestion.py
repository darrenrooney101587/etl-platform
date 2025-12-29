import io
import logging
from pathlib import Path
from typing import Any, Dict, List

import boto3
import pandas as pd
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from monitoring.models import (
    MonitoringFile,
    MonitoringFileDataQuality,
    MonitoringFileRun,
)
from monitoring.services.validation import extract_schema_columns, validate_bounds

logger = logging.getLogger(__name__)

BASE_SCORE = 100
DEDUCTIONS = {
    "schema_validation": 40,
    "format_parsing": 35,
    "completeness": 20,
    "bounds_range": 15,
    "uniqueness": 10,
}


class DataQualityResult:
    def __init__(self) -> None:
        self.metrics: Dict[str, Any] = {}
        self.deductions: Dict[str, Any] = {}
        self.failed_checks: List[str] = []

    def apply_deduction(self, key: str, reason: str, details: Any = None) -> None:
        self.deductions[key] = {
            "points": DEDUCTIONS[key],
            "reason": reason,
            "details": details,
        }
        self.failed_checks.append(key)

    @property
    def score(self) -> int:
        total_deductions = sum(DEDUCTIONS[key] for key in self.failed_checks)
        return max(0, BASE_SCORE - total_deductions)


def process_s3_file(bucket: str, key: str) -> MonitoringFileRun | None:
    logger.info("Processing S3 file", extra={"bucket": bucket, "key": key})
    monitoring_file = _resolve_monitoring_file(key)
    if not monitoring_file:
        logger.warning("No monitoring file configured for key", extra={"key": key})
        return None

    s3 = boto3.client("s3", region_name=settings.AWS_REGION)
    response = s3.get_object(Bucket=bucket, Key=key)
    file_bytes = response["Body"].read()
    file_size = response.get("ContentLength", len(file_bytes))

    run_date = timezone.now().date()
    run_hour = timezone.now().hour

    result = DataQualityResult()

    try:
        dataframe = _load_dataframe(file_bytes, key)
        result.metrics["row_count"] = len(dataframe)
        result.metrics["column_count"] = len(dataframe.columns)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to parse file", extra={"key": key})
        result.apply_deduction("format_parsing", "Failed to parse file", str(exc))
        return _persist_results(
            monitoring_file,
            file_size,
            run_date,
            run_hour,
            result,
        )

    schema_definition = monitoring_file.schema_definition
    if not schema_definition:
        logger.info(
            "No schema definition assigned; skipping detailed validation",
            extra={"monitoring_file_id": monitoring_file.id},
        )
        return _persist_results(
            monitoring_file,
            file_size,
            run_date,
            run_hour,
            result,
        )

    schema = schema_definition.definition or {}
    schema_columns, strict_mode = extract_schema_columns(schema)

    missing_columns = [col for col in schema_columns if col not in dataframe.columns]
    extra_columns = [col for col in dataframe.columns if col not in schema_columns]

    if missing_columns or (strict_mode and extra_columns):
        result.apply_deduction(
            "schema_validation",
            "Schema mismatch",
            {"missing": missing_columns, "extra": extra_columns},
        )
        result.metrics["missing_columns"] = missing_columns
        result.metrics["extra_columns"] = extra_columns

    if missing_columns:
        logger.info("Missing required columns; skipping further checks")
        return _persist_results(
            monitoring_file,
            file_size,
            run_date,
            run_hour,
            result,
        )

    required_columns = [
        column["name"]
        for column in schema.get("columns", [])
        if column.get("required")
    ]
    if required_columns:
        null_columns = [
            column
            for column in required_columns
            if dataframe[column].isnull().any()
        ]
        if null_columns:
            result.apply_deduction(
                "completeness",
                "Nulls in required columns",
                {"columns": null_columns},
            )
            result.metrics["null_columns"] = null_columns

    unique_columns = [
        column["name"]
        for column in schema.get("columns", [])
        if column.get("unique")
    ]
    if unique_columns:
        duplicate_columns = [
            column
            for column in unique_columns
            if not dataframe[column].is_unique
        ]
        if duplicate_columns:
            result.apply_deduction(
                "uniqueness",
                "Duplicate values found in unique columns",
                {"columns": duplicate_columns},
            )
            result.metrics["duplicate_columns"] = duplicate_columns

    bounds_failures = validate_bounds(schema.get("columns", []), dataframe)
    if bounds_failures:
        result.apply_deduction(
            "bounds_range",
            "Values outside expected bounds",
            bounds_failures,
        )
        result.metrics["bounds_failures"] = bounds_failures

    return _persist_results(
        monitoring_file,
        file_size,
        run_date,
        run_hour,
        result,
    )


def _resolve_monitoring_file(key: str) -> MonitoringFile | None:
    file_name = Path(key).name
    return MonitoringFile.objects.filter(file_name=file_name).first()


def _load_dataframe(file_bytes: bytes, key: str) -> pd.DataFrame:
    suffix = Path(key).suffix.lower()
    if suffix in {".xls", ".xlsx"}:
        return pd.read_excel(io.BytesIO(file_bytes))
    return pd.read_csv(io.BytesIO(file_bytes))


@transaction.atomic
def _persist_results(
    monitoring_file: MonitoringFile,
    file_size: int,
    run_date,
    run_hour: int,
    result: DataQualityResult,
) -> MonitoringFileRun:
    run = MonitoringFileRun.objects.create(
        monitoring_file=monitoring_file,
        file_size=file_size,
        run_date=run_date,
        run_hour=run_hour,
    )
    score = result.score
    passed = score >= settings.DATA_QUALITY_PASSING_SCORE

    MonitoringFileDataQuality.objects.create(
        monitoring_file_run=run,
        score=score,
        passed=passed,
        metrics=result.metrics,
        deductions=result.deductions,
    )

    MonitoringFile.objects.filter(id=monitoring_file.id).update(
        latest_data_quality_score=score
    )

    logger.info(
        "Data quality run completed",
        extra={
            "monitoring_file_id": monitoring_file.id,
            "score": score,
            "passed": passed,
        },
    )
    return run
