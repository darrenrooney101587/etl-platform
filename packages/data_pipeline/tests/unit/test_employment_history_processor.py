"""
Tests for the EmploymentHistoryProcessor class.

This module contains unit tests for all methods in the EmploymentHistoryProcessor class,
focusing on individual method behavior and employment history processing functionality.
"""
from data_pipeline.config.config import EmploymentHistoryConfig
from data_pipeline.processors.employment_history_processor import EmploymentHistoryProcessor
from data_pipeline.tests.unit.conftest import setup_mocks

setup_mocks()

import unittest
from unittest.mock import Mock, patch

class TestEmploymentHistoryProcessor(unittest.TestCase):
    """Test cases for EmploymentHistoryProcessor class methods.

    Provides setUp to replace pytest fixtures and allow unittest execution.
    """

    def setUp(self) -> None:
        """Prepare common fixtures for tests."""
        self.mock_s3_client = Mock()

        self.sample_employment_config = EmploymentHistoryConfig(
            agency_id=123,
            destination_bucket="test-destination-bucket",
            agency_s3_slug="test-agency-slug",
            destination_prefix="/downloads/",
            aws_access_key_id="test_access_key",
            aws_secret_access_key="test_secret_key",
            aws_region="us-gov-west-1",
        )

        self.sample_employment_data = [
            {
                "employee_id": "E001",
                "display_name": "IT Department",
                "effective_date": "2023-01-01",
                "employment_action": "HIRE",
                "title_rank": "Senior Developer",
                "employment_type": "Full-time",
                "comment": "Initial hire",
                "status": "Active",
                "supervisor": "John Manager",
                "tour_of_duty": "8x5",
                "role": "Developer",
            },
            {
                "employee_id": "E002",
                "display_name": "HR Department",
                "effective_date": "2023-02-01",
                "employment_action": "PROMOTION",
                "title_rank": "HR Manager",
                "employment_type": "Full-time",
                "comment": "Promoted to manager",
                "status": "Active",
                "supervisor": "Jane Director",
                "tour_of_duty": "8x5",
                "role": "Manager",
            },
        ]

    def test_init(self) -> None:
        """Test EmploymentHistoryProcessor initialization."""
        processor = EmploymentHistoryProcessor(self.sample_employment_config, self.mock_s3_client)

        self.assertEqual(processor.config, self.sample_employment_config)
        self.assertIs(processor.s3_client, self.mock_s3_client)
        self.assertIsNone(processor.data)

    @patch("data_pipeline.database.client.DatabaseClient.get_organization_employment_history")
    def test_fetch_data_success(self, mock_get_data: Mock) -> None:
        """Test successful data fetching."""
        processor = EmploymentHistoryProcessor(self.sample_employment_config, self.mock_s3_client)
        mock_get_data.return_value = self.sample_employment_data

        result = processor.fetch_data()

        mock_get_data.assert_called_once_with(self.sample_employment_config.agency_id)
        self.assertEqual(result, self.sample_employment_data)
        self.assertEqual(processor.data, self.sample_employment_data)

    @patch("data_pipeline.database.client.DatabaseClient.get_organization_employment_history")
    def test_fetch_data_exception(self, mock_get_data: Mock) -> None:
        """Test data fetching with exception."""
        processor = EmploymentHistoryProcessor(self.sample_employment_config, self.mock_s3_client)
        mock_get_data.side_effect = Exception("Database error")

        with self.assertRaisesRegex(Exception, "Database error"):
            processor.fetch_data()

        mock_get_data.assert_called_once_with(self.sample_employment_config.agency_id)
        self.assertIsNone(processor.data)

    def test_get_fieldnames(self) -> None:
        """Test getting CSV fieldnames."""
        processor = EmploymentHistoryProcessor(self.sample_employment_config, self.mock_s3_client)

        fieldnames = processor.get_fieldnames()

        expected_fields = [
            "display_name",
            "employee_id",
            "effective_date",
            "employment_action",
            "title_rank",
            "employment_type",
            "comment",
            "status",
            "supervisor",
            "tour_of_duty",
            "role",
        ]

        self.assertEqual(fieldnames, expected_fields)
        self.assertEqual(len(fieldnames), len(expected_fields))

    @patch("data_pipeline.processors.employment_history_processor.datetime")
    def test_get_filename(self, mock_datetime: Mock) -> None:
        """Test filename generation."""
        processor = EmploymentHistoryProcessor(self.sample_employment_config, self.mock_s3_client)

        mock_now = Mock()
        mock_now.strftime.return_value = "20231215_143000"
        mock_datetime.now.return_value = mock_now

        filename = processor.get_filename()

        expected_filename = f"employment_history_agency_{self.sample_employment_config.agency_id}_20231215_143000.csv"
        self.assertEqual(filename, expected_filename)

    def test_get_summary_no_data(self) -> None:
        """Test getting summary with no data."""
        processor = EmploymentHistoryProcessor(self.sample_employment_config, self.mock_s3_client)

        summary = processor.get_summary()

        self.assertEqual(summary["record_count"], 0)
        self.assertEqual(summary["agency_id"], self.sample_employment_config.agency_id)

    def test_get_summary_with_data(self) -> None:
        """Test getting summary with data."""
        processor = EmploymentHistoryProcessor(self.sample_employment_config, self.mock_s3_client)
        processor.data = self.sample_employment_data

        with patch.object(processor, "get_filename") as mock_get_filename:
            mock_get_filename.return_value = "test_filename.csv"

            summary = processor.get_summary()

            self.assertEqual(summary["agency_id"], self.sample_employment_config.agency_id)
            self.assertEqual(summary["record_count"], len(self.sample_employment_data))
            self.assertEqual(summary["filename"], "test_filename.csv")
            self.assertIn("data_fields", summary)
            self.assertIsInstance(summary["data_fields"], list)

    def test_upload_to_s3_with_existing_data(self) -> None:
        """Test S3 upload with existing data."""
        processor = EmploymentHistoryProcessor(self.sample_employment_config, self.mock_s3_client)
        processor.data = self.sample_employment_data

        with patch.object(processor, "upload_data_as_csv") as mock_upload:
            mock_upload.return_value = {"status": "success", "key": "test-key"}

            result = processor.upload_to_s3()

            mock_upload.assert_called_once_with(
                data=self.sample_employment_data,
                fieldnames=processor.get_fieldnames(),
                filename_prefix=f"employment_history_agency_{self.sample_employment_config.agency_id}",
                subfolder="employment_history",
                record_count_key="records_count",
            )

            self.assertEqual(result["status"], "success")

    @patch("data_pipeline.database.client.DatabaseClient.get_organization_employment_history")
    def test_upload_to_s3_without_existing_data(self, mock_get_data: Mock) -> None:
        """Test S3 upload without existing data (triggers fetch)."""
        processor = EmploymentHistoryProcessor(self.sample_employment_config, self.mock_s3_client)
        mock_get_data.return_value = self.sample_employment_data

        with patch.object(processor, "upload_data_as_csv") as mock_upload:
            mock_upload.return_value = {"status": "success", "key": "test-key"}

            result = processor.upload_to_s3()

            mock_get_data.assert_called_once_with(self.sample_employment_config.agency_id)

            mock_upload.assert_called_once_with(
                data=self.sample_employment_data,
                fieldnames=processor.get_fieldnames(),
                filename_prefix=f"employment_history_agency_{self.sample_employment_config.agency_id}",
                subfolder="employment_history",
                record_count_key="records_count",
            )

            self.assertEqual(result["status"], "success")

    def test_upload_to_s3_upload_failure(self) -> None:
        """Test S3 upload failure."""
        processor = EmploymentHistoryProcessor(self.sample_employment_config, self.mock_s3_client)
        processor.data = self.sample_employment_data

        with patch.object(processor, "upload_data_as_csv") as mock_upload:
            mock_upload.return_value = {"status": "error", "message": "Upload failed"}

            result = processor.upload_to_s3()

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["message"], "Upload failed")

    def test_inheritance_from_base_s3_client(self) -> None:
        """Test that EmploymentHistoryProcessor correctly inherits from S3Client."""
        processor = EmploymentHistoryProcessor(self.sample_employment_config, self.mock_s3_client)

        self.assertTrue(hasattr(processor, "_get_agency_folder"))
        self.assertTrue(hasattr(processor, "upload_csv_to_s3"))
        self.assertTrue(hasattr(processor, "upload_data_as_csv"))

        agency_folder = processor._get_agency_folder()
        self.assertEqual(agency_folder, self.sample_employment_config.agency_s3_slug)

    def test_data_persistence_across_methods(self) -> None:
        """Test that data persists across method calls."""
        processor = EmploymentHistoryProcessor(self.sample_employment_config, self.mock_s3_client)

        processor.data = self.sample_employment_data

        summary = processor.get_summary()
        self.assertEqual(summary["record_count"], len(self.sample_employment_data))

        self.assertEqual(processor.data, self.sample_employment_data)


if __name__ == "__main__":
    import unittest
    unittest.main()
