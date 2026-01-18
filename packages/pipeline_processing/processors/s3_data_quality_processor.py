"""S3 Data Quality Processor.

This processor implements the full data quality pipeline:
1. Parse S3 event to extract routing info
2. Look up monitoring file configuration
3. Download and parse the S3 object
4. Run validation checks (schema, format, completeness, bounds, uniqueness)
5. Compute deductions and score
6. Generate profiling payload
7. Persist results to the database
"""
from __future__ import annotations

import io
import logging
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from etl_core.database.client import DatabaseClient
from etl_core.s3.client import S3Client
from etl_core.config.config import S3Config
from pipeline_processing.models.events import S3Event, ParsedS3Key
from pipeline_processing.models.quality import (
    DataQualityDeductions,
    DataQualityMetrics,
    DataQualityResult,
    MetricResult,
)
from pipeline_processing.parsers import get_parser, ParseResult
from pipeline_processing.processors.profiler import DataProfiler
from pipeline_processing.repositories.monitoring_repository import MonitoringRepository
from pipeline_processing.validators import (
    BoundsValidator,
    CompletenessValidator,
    SchemaValidator,
    UniquenessValidator,
)

logger = logging.getLogger(__name__)


class S3DataQualityProcessorConfig:
    """Configuration for the S3 data quality processor."""

    def __init__(
        self,
        auto_create_monitoring_file: bool = False,
        generate_profile: bool = True,
        max_sample_rows: int = 50,
        max_distribution_items: int = 25,
        dry_run: bool = False,
        dry_run_output_path: Optional[str] = None,
    ) -> None:
        """Initialize processor configuration.

        Args:
            auto_create_monitoring_file: If True, create monitoring_file if not found.
            generate_profile: If True, generate and persist profiling data.
            max_sample_rows: Maximum sample rows in profile.
            max_distribution_items: Maximum distribution items per column.
            dry_run: If True, process data but do not persist results.
            dry_run_output_path: Optional path to write dry-run results (JSONL). Defaults to ./dry_run_results.jsonl.
        """
        # Default to NOT auto-creating monitoring_file/run. Upstream systems
        # are expected to create the run; the processor will error if run is
        # missing unless auto_create_monitoring_file=True is explicitly set.
        self.auto_create_monitoring_file = auto_create_monitoring_file
        self.generate_profile = generate_profile
        self.max_sample_rows = max_sample_rows
        self.max_distribution_items = max_distribution_items
        self.dry_run = dry_run
        self.dry_run_output_path = dry_run_output_path or "dry_run_results.jsonl"


class S3DataQualityProcessor:
    """Processor for S3 object data quality validation.

    This processor:
    1. Receives S3 events with bucket/key
    2. Downloads and parses the object
    3. Runs validation checks
    4. Computes scores and deductions
    5. Persists results to the database

    All external dependencies are injected via constructor for testability.
    """

    def __init__(
        self,
        repository: MonitoringRepository,
        s3_client: Optional[S3Client] = None,
        profiler: Optional[DataProfiler] = None,
        config: Optional[S3DataQualityProcessorConfig] = None,
    ) -> None:
        """Initialize the processor.

        Args:
            repository: MonitoringRepository for database operations.
            s3_client: Optional S3Client for downloading objects.
            profiler: Optional DataProfiler for generating profiles.
            config: Optional processor configuration.
        """
        self._repository = repository
        self._s3_client = s3_client
        self._profiler = profiler or DataProfiler()
        self._config = config or S3DataQualityProcessorConfig()

        # Initialize validators
        self._schema_validator = SchemaValidator()
        self._completeness_validator = CompletenessValidator()
        self._uniqueness_validator = UniquenessValidator()
        self._bounds_validator = BoundsValidator()

    def process_s3_event(self, event: S3Event) -> DataQualityResult:
        """Process an S3 event and compute data quality.

        This is the main entry point for the data quality pipeline.

        Args:
            event: S3Event with bucket, key, and optional metadata.

        Returns:
            DataQualityResult with score, metrics, deductions, and profile.

        Raises:
            ValueError: If the S3 key format is not recognized.
            RuntimeError: If monitoring file not found and auto-create is disabled.
        """
        logger.info(
            "Processing S3 event",
            extra={"bucket": event.bucket, "key": event.key},
        )

        # Step 1: Parse the S3 key
        try:
            parsed_key = event.parse_key()
        except ValueError as exc:
            logger.error("Failed to parse S3 key: %s", exc)
            raise

        # Step 2: Look up monitoring file
        # Pass the full key to help disambiguate files with the same name but different paths
        # Repository contract: get_monitoring_file(agency_slug, file_name)
        monitoring_file = self._repository.get_monitoring_file(parsed_key.agency_slug, parsed_key.file_name)

        if monitoring_file is None:
            if self._config.auto_create_monitoring_file:
                logger.info(
                    "Creating monitoring file for %s/%s",
                    parsed_key.agency_slug,
                    parsed_key.file_name,
                )
                monitoring_file = self._repository.create_monitoring_file(
                    parsed_key.agency_slug, parsed_key.file_name
                )
            else:
                raise RuntimeError(
                    f"Monitoring file not found: {parsed_key.agency_slug}/{parsed_key.file_name}"
                )

        # Respect suppression flag: if the monitoring file is suppressed we skip processing.
        # This prevents any profiling or data-quality writes for suppressed files.
        if getattr(monitoring_file, "is_suppressed", False):
            logger.info(
                "Monitoring file is suppressed; skipping data quality processing",
                extra={"monitoring_file_id": getattr(monitoring_file, "id", None)},
            )
            return DataQualityResult(
                score=100,
                passed=True,
                metrics=DataQualityMetrics(),
                deductions=DataQualityDeductions(),
                profile=None,
                failed_validation_message="suppressed",
                failed_validation_rules=None,
            )

        # Step 3: Get the run. Upstream systems are responsible for creating runs.
        # Try to get run by exact date/hour first (if parsed from key)
        run = None
        if hasattr(self._repository, "get_run"):
            run = self._repository.get_run(
                monitoring_file_id=monitoring_file.id,
                run_date=parsed_key.run_date,
                run_hour=parsed_key.run_hour,
            )

        # If not found by exact date/hour, try to get the latest run for this file
        if run is None and hasattr(self._repository, "get_latest_run"):
            logger.info(
                "Run not found for date=%s hour=%s; checking for latest run",
                parsed_key.run_date,
                parsed_key.run_hour,
            )
            run = self._repository.get_latest_run(monitoring_file_id=monitoring_file.id)

        # If still not found, if the repository supports get_or_create_run (test fakes), use it
        if run is None and hasattr(self._repository, "get_or_create_run"):
            logger.info("No existing run found; creating run via repository.get_or_create_run (test/dev)")
            run = self._repository.get_or_create_run(
                monitoring_file_id=monitoring_file.id,
                run_date=parsed_key.run_date,
                run_hour=parsed_key.run_hour,
            )

        # If still not found, fail (production safety)
        if run is None:
            raise RuntimeError(
                f"Monitoring run not found for monitoring_file_id={monitoring_file.id} "
                f"date={parsed_key.run_date} hour={parsed_key.run_hour} (or latest). "
                "Upstream system must create the monitoring_file_run before processing."
            )

        logger.info(
            "Processing run %d for monitoring_file %d",
            run.id,
            monitoring_file.id,
            extra={
                "monitoring_file_id": monitoring_file.id,
                "monitoring_file_run_id": run.id,
            },
        )

        # Step 4: Get schema definition if available
        schema_definition: Dict[str, Any] = {}
        if monitoring_file.schema_definition_id:
            schema_def = self._repository.get_schema_definition(
                monitoring_file.schema_definition_id,
                monitoring_file.schema_definition_version_id,
            )
            if schema_def:
                schema_definition = schema_def.definition

        # Step 5: Download and parse the object
        parse_result = self._download_and_parse(event, parsed_key.file_format)

        if not parse_result.success:
            # Format parsing failed - create failure result
            result = self._create_parse_failure_result(parse_result)
            self._persist_result(run.id, monitoring_file.id, result)
            return result

        # Step 6: Run validation checks
        result = self._run_validations(
            parse_result.rows,
            parse_result.columns,
            schema_definition,
        )

        # Step 7: Generate profile if enabled
        if self._config.generate_profile:
            result.profile = self._profiler.generate_profile(
                parse_result.rows,
                parse_result.columns,
                schema_definition,
            )

        # Step 8: Persist results
        self._persist_result(run.id, monitoring_file.id, result)

        logger.info(
            "Data quality processing complete",
            extra={
                "monitoring_file_id": monitoring_file.id,
                "monitoring_file_run_id": run.id,
                "score": result.score,
                "passed": result.passed,
            },
        )

        return result

    def process_bytes(
        self,
        data: bytes,
        file_format: str,
        schema_definition: Optional[Dict[str, Any]] = None,
    ) -> DataQualityResult:
        """Process raw bytes directly without S3 download.

        Useful for testing or when data is already in memory.

        Args:
            data: Raw file bytes.
            file_format: File format (csv, jsonl, parquet).
            schema_definition: Optional schema definition.

        Returns:
            DataQualityResult with quality metrics.
        """
        parser = get_parser(file_format)
        if parser is None:
            return self._create_parse_failure_result(
                ParseResult(
                    success=False,
                    error_message=f"No parser available for format: {file_format}",
                )
            )

        parse_result = parser.parse_bytes(data)

        if not parse_result.success:
            return self._create_parse_failure_result(parse_result)

        result = self._run_validations(
            parse_result.rows,
            parse_result.columns,
            schema_definition or {},
        )

        if self._config.generate_profile:
            result.profile = self._profiler.generate_profile(
                parse_result.rows,
                parse_result.columns,
                schema_definition,
            )

        return result

    def _download_and_parse(
        self,
        event: S3Event,
        file_format: str,
    ) -> ParseResult:
        """Download S3 object and parse it.

        Args:
            event: S3Event with bucket and key.
            file_format: Expected file format.

        Returns:
            ParseResult from parsing the file.
        """
        # Check for local S3 root override
        local_s3_root = os.getenv("LOCAL_S3_ROOT")
        if local_s3_root:
            try:
                # Construct local path
                # Remove leading slash from key if present to join correctly
                key_path = event.key.lstrip("/")
                local_path = Path(local_s3_root) / key_path

                logger.info("Reading from local file: %s", local_path)

                if not local_path.exists():
                    # Fallback: try to find the file anywhere under the local_s3_root
                    file_name = Path(key_path).name
                    logger.info(
                        "Local file not found at expected path; searching for '%s' under %s",
                        file_name,
                        local_s3_root,
                    )
                    try:
                        root_path = Path(local_s3_root)
                        # Use rglob to search recursively for the filename
                        matches = list(root_path.rglob(file_name))
                        if matches:
                            local_path = matches[0]
                            logger.info("Found local file via search: %s", local_path)
                        else:
                            return ParseResult(
                                success=False,
                                error_message=f"Local file not found: {local_path}",
                            )
                    except Exception as exc:
                        logger.exception("Error while searching for local file")
                        return ParseResult(
                            success=False,
                            error_message=f"Local file not found and search failed: {exc}",
                        )

                parser = get_parser(file_format)
                if parser is None:
                    return ParseResult(
                        success=False,
                        error_message=f"No parser available for format: {file_format}",
                    )

                with open(local_path, "rb") as f:
                    return parser.parse(f)
            except Exception as exc:
                logger.exception("Failed to read/parse local file")
                return ParseResult(
                    success=False,
                    error_message=f"Failed to read local file: {exc}",
                )

        if self._s3_client is None:
            return ParseResult(
                success=False,
                error_message="S3 client not configured",
            )

        parser = get_parser(file_format)
        if parser is None:
            return ParseResult(
                success=False,
                error_message=f"No parser available for format: {file_format}",
            )

        try:
            response = self._s3_client.s3_client.get_object(
                Bucket=event.bucket,
                Key=event.key,
            )
            return parser.parse(response["Body"])
        except Exception as exc:
            # If this is a botocore ClientError, check for NoSuchKey and return a clear message
            try:
                from botocore.exceptions import ClientError

                if isinstance(exc, ClientError):
                    err_code = exc.response.get("Error", {}).get("Code")
                    if err_code == "NoSuchKey":
                        s3_url = f"s3://{event.bucket}/{event.key}"
                        logger.error(
                            "S3 object not found: %s (NoSuchKey). Ensure the event key is correct and the object exists.",
                            s3_url,
                        )
                        return ParseResult(success=False, error_message=f"NoSuchKey: {s3_url}")
            except Exception:
                # ignore errors while introspecting exception
                pass

            logger.exception("Failed to download/parse S3 object")
            return ParseResult(
                success=False,
                error_message=f"Failed to download S3 object: {exc}",
            )

    def _run_validations(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        schema_definition: Dict[str, Any],
    ) -> DataQualityResult:
        """Run all validation checks and compute score.

        Args:
            rows: Parsed data rows.
            columns: Column names.
            schema_definition: Schema definition.

        Returns:
            DataQualityResult with all metrics and deductions.
        """
        deductions = DataQualityDeductions()
        metrics = DataQualityMetrics()
        failed_rules: List[Dict[str, Any]] = []

        # Format parsing passed (we got here)
        metrics.format_parsing = MetricResult(
            passed=True,
            details=f"File parsed successfully ({len(rows)} rows, {len(columns)} columns)",
        )

        # Schema validation
        schema_result = self._schema_validator.validate(rows, columns, schema_definition)
        metrics.schema_validation = MetricResult(
            passed=schema_result.passed,
            details=schema_result.details,
            metadata=schema_result.metadata,
        )
        if not schema_result.passed:
            # Proportional deduction
            ratio = schema_result.failure_ratio
            deductions.schema = ratio * DataQualityDeductions.MAX_SCHEMA
            failed_rules.extend(schema_result.failures)

        # Completeness validation
        completeness_result = self._completeness_validator.validate(
            rows, columns, schema_definition
        )
        metrics.completeness = MetricResult(
            passed=completeness_result.passed,
            details=completeness_result.details,
            metadata=completeness_result.metadata,
        )
        if not completeness_result.passed:
            ratio = completeness_result.failure_ratio
            deductions.completeness = ratio * DataQualityDeductions.MAX_COMPLETENESS
            failed_rules.extend(completeness_result.failures)

        # Uniqueness validation
        uniqueness_result = self._uniqueness_validator.validate(
            rows, columns, schema_definition
        )
        metrics.uniqueness = MetricResult(
            passed=uniqueness_result.passed,
            details=uniqueness_result.details,
            metadata=uniqueness_result.metadata,
        )
        if not uniqueness_result.passed:
            ratio = uniqueness_result.failure_ratio
            deductions.uniqueness = ratio * DataQualityDeductions.MAX_UNIQUENESS
            failed_rules.extend(uniqueness_result.failures)

        # Bounds validation
        bounds_result = self._bounds_validator.validate(rows, columns, schema_definition)
        metrics.bounds_range = MetricResult(
            passed=bounds_result.passed,
            details=bounds_result.details,
            metadata=bounds_result.metadata,
        )
        if not bounds_result.passed:
            ratio = bounds_result.failure_ratio
            deductions.bounds = ratio * DataQualityDeductions.MAX_BOUNDS
            failed_rules.extend(bounds_result.failures)

        # Compute final score
        score = DataQualityResult.compute_score(deductions)
        passed = DataQualityResult.is_passed(score)

        # Build failure message if not passed
        failed_message: Optional[str] = None
        if not passed:
            failed_dims = []
            if not metrics.schema_validation.passed:
                failed_dims.append("schema")
            if not metrics.format_parsing.passed:
                failed_dims.append("format")
            if not metrics.completeness.passed:
                failed_dims.append("completeness")
            if not metrics.bounds_range.passed:
                failed_dims.append("bounds")
            if not metrics.uniqueness.passed:
                failed_dims.append("uniqueness")
            failed_message = f"Quality check failed in: {', '.join(failed_dims)}"

        return DataQualityResult(
            score=score,
            passed=passed,
            metrics=metrics,
            deductions=deductions,
            failed_validation_message=failed_message,
            failed_validation_rules=failed_rules if failed_rules else None,
        )

    def _create_parse_failure_result(self, parse_result: ParseResult) -> DataQualityResult:
        """Create a result for a parse failure.

        Args:
            parse_result: Failed ParseResult.

        Returns:
            DataQualityResult with format deduction.
        """
        deductions = DataQualityDeductions(format=DataQualityDeductions.MAX_FORMAT)
        metrics = DataQualityMetrics()
        metrics.format_parsing = MetricResult(
            passed=False,
            details=parse_result.error_message or "Failed to parse file",
        )

        score = DataQualityResult.compute_score(deductions)
        # Treat parse failures as hard failures regardless of computed score
        passed = False

        return DataQualityResult(
            score=score,
            passed=passed,
            metrics=metrics,
            deductions=deductions,
            failed_validation_message=parse_result.error_message,
            failed_validation_rules=[{
                "check": "format_parsing",
                "message": parse_result.error_message,
            }],
        )

    def _persist_result(
        self,
        run_id: int,
        monitoring_file_id: int,
        result: DataQualityResult,
    ) -> None:
        """Persist the quality result to the database.

        Args:
            run_id: MonitoringFileRun ID.
            monitoring_file_id: MonitoringFile ID.
            result: DataQualityResult to persist.
        """
        if self._config.dry_run:
            logger.info(
                "Dry-run enabled; skipping persistence",
                extra={
                    "monitoring_file_id": monitoring_file_id,
                    "monitoring_file_run_id": run_id,
                },
            )
            # Write dry-run output to file
            try:
                output_path = self._config.dry_run_output_path or "dry_run_results.jsonl"
                abs_path = os.path.abspath(output_path)
                dirpath = os.path.dirname(abs_path)
                logger.info("Writing dry-run output to: %s", abs_path)

                # Ensure directory exists if a directory component was provided
                if dirpath:
                    try:
                        os.makedirs(dirpath, exist_ok=True)
                    except Exception:
                        # If dirpath is empty or invalid, fall back to current directory
                        dirpath = "."

                # Append result to dry-run output file (JSONL). Use default=str for non-serializable types.
                with open(abs_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(result.to_dict(), default=str) + "\n")
            except Exception as exc:
                logger.error("Failed to write dry-run output: %s", exc)
            return
        self._repository.upsert_data_quality(
            monitoring_file_run_id=run_id,
            monitoring_file_id=monitoring_file_id,
            score=result.score,
            passed=result.passed,
            metrics=result.metrics.to_dict(),
            deductions=result.deductions.to_dict(),
            failed_validation_message=result.failed_validation_message,
            failed_validation_rules=result.failed_validation_rules,
        )

        if result.profile is not None:
            self._repository.upsert_data_profile(
                monitoring_file_run_id=run_id,
                monitoring_file_id=monitoring_file_id,
                profile_payload=result.profile.to_dict(),
            )

        self._repository.update_monitoring_file_score(monitoring_file_id, result.score)
