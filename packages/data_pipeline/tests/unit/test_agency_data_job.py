import sys
from unittest.mock import MagicMock, Mock, patch
import unittest

from data_pipeline.jobs.agency_data_job import AgencyDataJob
from data_pipeline.tests.unit.conftest import setup_mocks

setup_mocks()

class TestAgencyDataJob(unittest.TestCase):
    """Unit tests for AgencyDataJob dry_run behavior."""

    def setUp(self) -> None:
        self.service = AgencyDataJob(
            source_bucket="src-bucket",
            destination_bucket="dst-bucket",
        )

    @patch("etl_core.database.client.DatabaseClient.get_organization_employment_history", return_value=[1, 2, 3])
    @patch.object(AgencyDataJob, "_create_s3_processor")
    @patch.object(AgencyDataJob, "_create_employment_history_processor")
    @patch("etl_core.database.client.DatabaseClient.get_agency_s3_slug")
    @patch("etl_core.database.client.DatabaseClient.get_attachment_files_for_s3_processing")
    def test_process_agency_files_dry_run_no_external_calls(
        self,
        mock_get_files: MagicMock,
        mock_get_slug: MagicMock,
        mock_create_eh: MagicMock,
        mock_create_s3: MagicMock,
        mock_get_organization_employment_history: MagicMock,
    ) -> None:
        """When dry_run is True, do not instantiate S3 processor or upload anything."""
        mock_get_files.return_value = [
            {"attachable_type": "Form", "byte_size": 100},
            {"attachable_type": "UserDocument", "byte_size": 200},
        ]
        mock_get_slug.return_value = "agency-slug"

        # Employment history processor fetch is allowed (read-only)
        mock_eh = Mock()
        mock_eh.fetch_data.return_value = [1, 2, 3]
        mock_create_eh.return_value = mock_eh

        result = self.service.process_agency_files(agency_id=10, dry_run=True)

        # External processor should not be created in dry-run
        mock_create_s3.assert_not_called()

        self.assertEqual(result["status"], "success")
        self.assertTrue(result.get("dry_run", False))
        self.assertEqual(result["results"]["files_planned"], 2)
        self.assertEqual(result["results"]["employment_records"], 3)
        self.assertEqual(result["results"]["files_processed"], 0)

    @patch("etl_core.database.client.DatabaseClient.get_organization_employment_history", return_value=[1, 2, 3])
    @patch.object(AgencyDataJob, "_process_employment_history")
    @patch.object(AgencyDataJob, "_create_s3_processor")
    @patch("etl_core.database.client.DatabaseClient.get_agency_s3_slug")
    @patch("etl_core.database.client.DatabaseClient.get_attachment_files_for_s3_processing")
    def test_process_agency_files_executes_when_not_dry_run(
        self,
        mock_get_files: MagicMock,
        mock_get_slug: MagicMock,
        mock_create_s3: MagicMock,
        mock_proc_eh: MagicMock,
        mock_get_organization_employment_history: MagicMock,
    ) -> None:
        """When dry_run is False, processing path is executed and results aggregated."""
        mock_get_files.return_value = [
            {"attachable_type": "Form", "byte_size": 100},
            {"attachable_type": "UserDocument", "byte_size": 200},
        ]
        mock_get_slug.return_value = "agency-slug"

        # Mock S3 processor behavior
        mock_processor = Mock()
        mock_processor.process_files.return_value = [
            {"status": "success", "source_key": "a"},
            {"status": "error", "source_key": "b", "message": "fail"},
        ]
        mock_processor.upload_metadata_csv.return_value = {"status": "success"}
        mock_create_s3.return_value = mock_processor

        mock_proc_eh.return_value = {"status": "success", "records_count": 3}

        result = self.service.process_agency_files(agency_id=10, dry_run=False)

        mock_create_s3.assert_called_once()
        mock_processor.process_files.assert_called_once()
        mock_processor.upload_metadata_csv.assert_called_once()
        mock_proc_eh.assert_called_once()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["results"]["files_processed"], 2)
        self.assertEqual(result["results"]["files_successful"], 1)
        self.assertEqual(result["results"]["files_failed"], 1)
