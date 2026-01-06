"""Unit tests for S3DataQualityProcessor."""
import unittest
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from file_processing.models.events import S3Event
from file_processing.models.monitoring import (
    MonitoringFile,
    MonitoringFileDataQuality,
    MonitoringFileRun,
    MonitoringFileSchemaDefinition,
)
from file_processing.processors.s3_data_quality_processor import (
    S3DataQualityProcessor,
    S3DataQualityProcessorConfig,
)


class FakeMonitoringRepository:
    """Fake repository for testing S3DataQualityProcessor."""

    def __init__(self) -> None:
        self.monitoring_files: Dict[str, MonitoringFile] = {}
        self.schema_definitions: Dict[int, MonitoringFileSchemaDefinition] = {}
        self.runs: Dict[int, MonitoringFileRun] = {}
        self.quality_results: Dict[int, MonitoringFileDataQuality] = {}
        self.profiles: Dict[int, Dict[str, Any]] = {}
        self._next_id = 1

    def get_monitoring_file(
        self, agency_slug: str, file_name: str
    ) -> Optional[MonitoringFile]:
        key = f"{agency_slug}/{file_name}"
        return self.monitoring_files.get(key)

    def get_monitoring_file_by_id(
        self, monitoring_file_id: int
    ) -> Optional[MonitoringFile]:
        for mf in self.monitoring_files.values():
            if mf.id == monitoring_file_id:
                return mf
        return None

    def create_monitoring_file(
        self,
        agency_slug: str,
        file_name: str,
        schema_definition_id: Optional[int] = None,
    ) -> MonitoringFile:
        mf = MonitoringFile(
            id=self._next_id,
            file_name=file_name,
            agency_slug=agency_slug,
            schema_definition_id=schema_definition_id,
        )
        self._next_id += 1
        self.monitoring_files[f"{agency_slug}/{file_name}"] = mf
        return mf

    def update_monitoring_file_score(
        self, monitoring_file_id: int, score: int
    ) -> None:
        for mf in self.monitoring_files.values():
            if mf.id == monitoring_file_id:
                mf.latest_data_quality_score = score
                break

    def get_schema_definition(
        self, schema_definition_id: int
    ) -> Optional[MonitoringFileSchemaDefinition]:
        return self.schema_definitions.get(schema_definition_id)

    def get_or_create_run(
        self,
        monitoring_file_id: int,
        run_date: date,
        run_hour: int,
        agency_id: Optional[int] = None,
        file_last_modified: Optional[datetime] = None,
        file_size: Optional[int] = None,
    ) -> MonitoringFileRun:
        key = (monitoring_file_id, run_date, run_hour)
        for run in self.runs.values():
            if (run.monitoring_file_id, run.run_date, run.run_hour) == key:
                return run

        run = MonitoringFileRun(
            id=self._next_id,
            monitoring_file_id=monitoring_file_id,
            run_date=run_date,
            run_hour=run_hour,
            agency_id=agency_id,
            file_last_modified=file_last_modified,
            file_size=file_size,
        )
        self._next_id += 1
        self.runs[run.id] = run
        return run

    def upsert_data_quality(
        self,
        monitoring_file_run_id: int,
        monitoring_file_id: Optional[int],
        score: int,
        passed: bool,
        metrics: Dict[str, Any],
        deductions: Dict[str, float],
        failed_validation_message: Optional[str] = None,
        failed_validation_rules: Optional[List[Dict[str, Any]]] = None,
    ) -> MonitoringFileDataQuality:
        quality = MonitoringFileDataQuality(
            id=self._next_id,
            monitoring_file_run_id=monitoring_file_run_id,
            monitoring_file_id=monitoring_file_id,
            score=score,
            passed=passed,
            metrics=metrics,
            deductions=deductions,
            failed_validation_message=failed_validation_message,
            failed_validation_rules=failed_validation_rules,
        )
        self._next_id += 1
        self.quality_results[monitoring_file_run_id] = quality
        return quality

    def upsert_data_profile(
        self, monitoring_file_run_id: int, monitoring_file_id: Optional[int], profile_payload: Dict[str, Any]
    ) -> Any:
        # Store both run and file id for verification
        self.profiles[monitoring_file_run_id] = {
            "monitoring_file_id": monitoring_file_id,
            "profile": profile_payload,
        }
        return MagicMock(id=self._next_id)


class S3DataQualityProcessorTest(unittest.TestCase):
    """Tests for S3DataQualityProcessor."""

    def test_process_bytes_valid_csv(self) -> None:
        """Test processing valid CSV bytes."""
        repo = FakeMonitoringRepository()
        config = S3DataQualityProcessorConfig(generate_profile=True)
        processor = S3DataQualityProcessor(repository=repo, config=config)

        csv_data = b"id,name,age\n1,Alice,30\n2,Bob,25"
        schema = {
            "columns": [
                {"name": "id", "type": "integer", "required": True, "nullable": False, "unique": True},
                {"name": "name", "type": "string", "required": True, "nullable": False},
                {"name": "age", "type": "integer", "required": True, "nullable": False, "min": 0, "max": 150},
            ]
        }

        result = processor.process_bytes(csv_data, "csv", schema)

        self.assertEqual(result.score, 100)
        self.assertTrue(result.passed)
        self.assertTrue(result.metrics.format_parsing.passed)
        self.assertTrue(result.metrics.schema_validation.passed)

    def test_process_bytes_parse_failure(self) -> None:
        """Test processing invalid file returns format deduction."""
        repo = FakeMonitoringRepository()
        processor = S3DataQualityProcessor(repository=repo)

        result = processor.process_bytes(b"\xff\xfe invalid", "csv", {})

        self.assertFalse(result.passed)
        self.assertFalse(result.metrics.format_parsing.passed)
        self.assertEqual(result.deductions.format, 35.0)

    def test_process_bytes_unknown_format(self) -> None:
        """Test processing with unknown format."""
        repo = FakeMonitoringRepository()
        processor = S3DataQualityProcessor(repository=repo)

        result = processor.process_bytes(b"data", "unknown", {})

        self.assertFalse(result.passed)
        self.assertIn("No parser available", result.failed_validation_message)

    def test_process_bytes_with_schema_violations(self) -> None:
        """Test processing data that violates schema."""
        repo = FakeMonitoringRepository()
        processor = S3DataQualityProcessor(repository=repo)

        csv_data = b"id,name\n1,Alice\n1,Bob"  # Duplicate ID
        schema = {
            "columns": [
                {"name": "id", "type": "integer", "required": True, "unique": True},
            ],
            "unique_keys": ["id"],
        }

        result = processor.process_bytes(csv_data, "csv", schema)

        self.assertFalse(result.metrics.uniqueness.passed)
        self.assertGreater(result.deductions.uniqueness, 0)

    def test_process_bytes_with_completeness_issues(self) -> None:
        """Test processing data with null values in required fields."""
        repo = FakeMonitoringRepository()
        processor = S3DataQualityProcessor(repository=repo)

        csv_data = b"id,name\n1,Alice\n2,"  # Missing name
        schema = {
            "columns": [
                {"name": "id", "type": "integer", "required": True, "nullable": False},
                {"name": "name", "type": "string", "required": True, "nullable": False},
            ]
        }

        result = processor.process_bytes(csv_data, "csv", schema)

        self.assertFalse(result.metrics.completeness.passed)
        self.assertGreater(result.deductions.completeness, 0)

    def test_process_bytes_generates_profile(self) -> None:
        """Test that profiling is generated when enabled."""
        repo = FakeMonitoringRepository()
        config = S3DataQualityProcessorConfig(generate_profile=True)
        processor = S3DataQualityProcessor(repository=repo, config=config)

        csv_data = b"id,name\n1,Alice\n2,Bob"

        result = processor.process_bytes(csv_data, "csv", {})

        self.assertIsNotNone(result.profile)
        profile_dict = result.profile.to_dict()
        self.assertIn("statisticalSummary", profile_dict)
        self.assertIn("sampleData", profile_dict)

    def test_process_bytes_skips_profile_when_disabled(self) -> None:
        """Test that profiling is skipped when disabled."""
        repo = FakeMonitoringRepository()
        config = S3DataQualityProcessorConfig(generate_profile=False)
        processor = S3DataQualityProcessor(repository=repo, config=config)

        csv_data = b"id,name\n1,Alice"

        result = processor.process_bytes(csv_data, "csv", {})

        self.assertIsNone(result.profile)


class S3DataQualityProcessorS3EventTest(unittest.TestCase):
    """Tests for S3DataQualityProcessor.process_s3_event()."""

    def test_process_s3_event_creates_monitoring_file(self) -> None:
        """Test that auto-create works for new monitoring files."""
        repo = FakeMonitoringRepository()
        config = S3DataQualityProcessorConfig(auto_create_monitoring_file=True)

        # Create a mock S3 client that returns CSV data
        mock_s3_client = MagicMock()
        mock_s3_client.s3_client.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"id,name\n1,Alice")
        }

        processor = S3DataQualityProcessor(
            repository=repo, s3_client=mock_s3_client, config=config
        )

        event = S3Event(
            bucket="test-bucket",
            key="agency/new-agency/files/new-file/2026-01-04/12/data.csv",
        )

        result = processor.process_s3_event(event)

        # Monitoring file should have been created
        self.assertIn("new-agency/new-file", repo.monitoring_files)
        self.assertTrue(result.passed)

    def test_process_s3_event_fails_without_auto_create(self) -> None:
        """Test that processing fails when monitoring file not found and auto-create disabled."""
        repo = FakeMonitoringRepository()
        config = S3DataQualityProcessorConfig(auto_create_monitoring_file=False)
        processor = S3DataQualityProcessor(repository=repo, config=config)

        event = S3Event(
            bucket="test-bucket",
            key="agency/unknown/files/unknown-file/2026-01-04/12/data.csv",
        )

        with self.assertRaises(RuntimeError) as ctx:
            processor.process_s3_event(event)

        self.assertIn("Monitoring file not found", str(ctx.exception))

    def test_process_s3_event_persists_results(self) -> None:
        """Test that results are persisted to the repository."""
        repo = FakeMonitoringRepository()
        # Pre-create monitoring file
        mf = repo.create_monitoring_file("test-agency", "test-file")

        mock_s3_client = MagicMock()
        mock_s3_client.s3_client.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"id,name\n1,Alice")
        }

        processor = S3DataQualityProcessor(repository=repo, s3_client=mock_s3_client)

        event = S3Event(
            bucket="test-bucket",
            key="agency/test-agency/files/test-file/2026-01-04/12/data.csv",
        )

        result = processor.process_s3_event(event)

        # Check that run was created
        self.assertEqual(len(repo.runs), 1)

        # Check that quality result was stored
        self.assertEqual(len(repo.quality_results), 1)

        # Check that score was updated on monitoring file
        self.assertEqual(mf.latest_data_quality_score, result.score)


if __name__ == "__main__":
    unittest.main()
