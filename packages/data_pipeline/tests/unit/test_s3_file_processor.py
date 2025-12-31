"""
Tests for the S3FileProcessor class.

This module contains unit tests for all methods in the S3FileProcessor class,
focusing on individual method behavior and file processing functionality.
"""
from packages.data_pipeline.config.config import S3Config
from packages.data_pipeline.processors.s3_file_processor import S3FileProcessor
from packages.data_pipeline.tests.unit.conftest import setup_mocks

setup_mocks()

import unittest
from unittest.mock import Mock, patch, MagicMock, call

from botocore.exceptions import ClientError


class TestS3FileProcessor(unittest.TestCase):
    """Test cases for S3FileProcessor class methods.

    setUp provides sample_s3_config, mock_s3_client and sample test data to replace pytest fixtures.
    """

    def setUp(self) -> None:
        self.mock_s3_client = Mock()
        self.mock_s3_client.head_object.return_value = {"ContentLength": 1024}
        self.mock_s3_client.copy_object.return_value = {}
        self.mock_s3_client.put_object.return_value = {}

        self.sample_s3_config = S3Config(
            source_bucket="test-source-bucket",
            destination_bucket="test-destination-bucket",
            agency_s3_slug="test-agency-slug",
            agency_id=123,
            destination_prefix="/downloads/",
            aws_access_key_id="test_access_key",
            aws_secret_access_key="test_secret_key",
            aws_region="us-gov-west-1",
            max_workers=3,
            retry_attempts=2,
        )

        self.sample_file_mappings = [
            {
                "filename": "test_file_1.pdf",
                "output_filename": "renamed_file_1.pdf",
                "original_filename": "original_1.pdf",
                "mime_type": "application/pdf",
                "byte_size": 1024,
            },
            {
                "filename": "test_file_2.jpg",
                "output_filename": "renamed_file_2.jpg",
                "original_filename": "original_2.jpg",
                "mime_type": "image/jpeg",
                "byte_size": 2048,
            },
        ]

        self.sample_query_results = [
            {
                "id": 1,
                "filename": "test_file_1.pdf",
                "mime_type": "application/pdf",
                "created": "2023-01-01T12:00:00",
                "user_id": 101,
            },
            {
                "id": 2,
                "filename": "test_file_2.jpg",
                "mime_type": "image/jpeg",
                "created": "2023-01-02T12:00:00",
                "user_id": 102,
            },
        ]

    def test_init(self) -> None:
        """Test S3FileProcessor initialization."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        self.assertEqual(processor.config, self.sample_s3_config)
        self.assertIs(processor.s3_client, self.mock_s3_client)
        self.assertIsNone(processor._progress_callback)

    def test_set_progress_callback(self) -> None:
        """Test setting progress callback."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)
        callback = Mock()

        processor.set_progress_callback(callback)

        self.assertIs(processor._progress_callback, callback)

    @patch("data_pipeline.processors.s3_file_processor.ThreadPoolExecutor")
    def test_process_files_success(self, mock_executor_class: Mock) -> None:
        """Test successful file processing."""

        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        # Mock executor and futures
        mock_executor = Mock()
        mock_executor_class.return_value.__enter__ = Mock(return_value=mock_executor)
        mock_executor_class.return_value.__exit__ = Mock(return_value=None)

        mock_future1 = Mock()
        mock_future2 = Mock()
        mock_future1.result.return_value = {"status": "success", "source_key": "file1"}
        mock_future2.result.return_value = {"status": "success", "source_key": "file2"}

        mock_executor.submit.side_effect = [mock_future1, mock_future2]

        with patch("data_pipeline.processors.s3_file_processor.as_completed") as mock_as_completed:
            mock_as_completed.return_value = [mock_future1, mock_future2]

            results = processor.process_files(self.sample_file_mappings)

            self.assertEqual(len(results), 2)
            self.assertTrue(all(result["status"] == "success" for result in results))

            # Ensure ThreadPoolExecutor was instantiated with expected max_workers.
            self.assertTrue(mock_executor_class.called)
            _, called_kwargs = mock_executor_class.call_args
            self.assertEqual(called_kwargs.get("max_workers"), self.sample_s3_config.max_workers)
            self.assertEqual(mock_executor.submit.call_count, 2)

    @patch("data_pipeline.processors.s3_file_processor.ThreadPoolExecutor")
    def test_process_files_with_callback(self, mock_executor_class: Mock) -> None:
        """Test file processing with progress callback."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)
        callback = Mock()
        processor.set_progress_callback(callback)

        mock_executor = Mock()
        mock_executor_class.return_value.__enter__ = Mock(return_value=mock_executor)
        mock_executor_class.return_value.__exit__ = Mock(return_value=None)

        mock_future = Mock()
        mock_future.result.return_value = {"status": "success"}
        mock_executor.submit.return_value = mock_future

        with patch("data_pipeline.processors.s3_file_processor.as_completed") as mock_as_completed:
            mock_as_completed.return_value = [mock_future]

            processor.process_files([self.sample_file_mappings[0]])

            callback.assert_called_once_with(1, 1, self.sample_file_mappings[0]["filename"])

    def test_copy_single_file_success(self) -> None:
        """Test successful single file copy."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        self.mock_s3_client.head_object.return_value = {"ContentLength": 1024}

        mapping = {"filename": "test_file.pdf", "output_filename": "renamed_file.pdf"}

        result = processor._copy_single_file(mapping)

        self.mock_s3_client.head_object.assert_called_once_with(
            Bucket=self.sample_s3_config.source_bucket, Key="test_file.pdf"
        )

        expected_dest_key = f"{self.sample_s3_config.agency_s3_slug}{self.sample_s3_config.destination_prefix.rstrip('/')}/renamed_file.pdf"
        self.mock_s3_client.copy_object.assert_called_once_with(
            CopySource={"Bucket": self.sample_s3_config.source_bucket, "Key": "test_file.pdf"},
            Bucket=self.sample_s3_config.destination_bucket,
            Key=expected_dest_key,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["source_key"], "test_file.pdf")
        self.assertEqual(result["destination_key"], expected_dest_key)
        self.assertEqual(result["file_size"], 1024)

    def test_copy_single_file_missing_filename(self) -> None:
        """Test single file copy with missing filename."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        mapping = {"output_filename": "renamed_file.pdf"}

        result = processor._copy_single_file(mapping)

        self.assertEqual(result["status"], "error")
        self.assertIn("Missing filename or output_filename", result["message"])
        self.mock_s3_client.head_object.assert_not_called()
        self.mock_s3_client.copy_object.assert_not_called()

    def test_copy_single_file_missing_output_filename(self) -> None:
        """Test single file copy with missing output filename."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        mapping = {"filename": "test_file.pdf"}

        result = processor._copy_single_file(mapping)

        self.assertEqual(result["status"], "error")
        self.assertIn("Missing filename or output_filename", result["message"])

    def test_copy_single_file_not_found(self) -> None:
        """Test single file copy when source file not found."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        error_response = {"Error": {"Code": "NoSuchKey", "Message": "Key not found"}}
        self.mock_s3_client.head_object.side_effect = ClientError(error_response, "HeadObject")

        mapping = {"filename": "nonexistent_file.pdf", "output_filename": "renamed_file.pdf"}

        result = processor._copy_single_file(mapping)

        self.assertEqual(result["status"], "not_found")
        self.assertIn("File not found", result["message"])
        self.mock_s3_client.copy_object.assert_not_called()

    def test_copy_single_file_404_error(self) -> None:
        """Test single file copy with 404 error."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        error_response = {"Error": {"Code": "404", "Message": "Not found"}}
        self.mock_s3_client.head_object.side_effect = ClientError(error_response, "HeadObject")

        mapping = {"filename": "nonexistent_file.pdf", "output_filename": "renamed_file.pdf"}

        result = processor._copy_single_file(mapping)

        self.assertEqual(result["status"], "not_found")
        self.assertIn("File not found", result["message"])

    @patch("data_pipeline.processors.s3_file_processor.time.sleep")
    def test_copy_single_file_retry_success(self, mock_sleep: Mock) -> None:
        """Test single file copy with retry success."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        error_response = {"Error": {"Code": "InternalError", "Message": "Server error"}}
        self.mock_s3_client.head_object.side_effect = [ClientError(error_response, "HeadObject"), {"ContentLength": 1024}]

        mapping = {"filename": "test_file.pdf", "output_filename": "renamed_file.pdf"}

        result = processor._copy_single_file(mapping)

        self.assertEqual(result["status"], "success")
        self.assertEqual(self.mock_s3_client.head_object.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    @patch("data_pipeline.processors.s3_file_processor.time.sleep")
    def test_copy_single_file_retry_exhausted(self, mock_sleep: Mock) -> None:
        """Test single file copy with retry exhausted."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        error_response = {"Error": {"Code": "InternalError", "Message": "Server error"}}
        self.mock_s3_client.head_object.side_effect = ClientError(error_response, "HeadObject")

        mapping = {"filename": "test_file.pdf", "output_filename": "renamed_file.pdf"}

        result = processor._copy_single_file(mapping)

        self.assertEqual(result["status"], "error")
        self.assertIn("AWS error (InternalError)", result["message"])
        self.assertEqual(self.mock_s3_client.head_object.call_count, self.sample_s3_config.retry_attempts)
        self.assertEqual(mock_sleep.call_count, self.sample_s3_config.retry_attempts - 1)

    @patch("data_pipeline.processors.s3_file_processor.time.sleep")
    def test_copy_single_file_unexpected_error_retry(self, mock_sleep: Mock) -> None:
        """Test single file copy with unexpected error and retry."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        self.mock_s3_client.head_object.side_effect = ValueError("Unexpected error")

        mapping = {"filename": "test_file.pdf", "output_filename": "renamed_file.pdf"}

        result = processor._copy_single_file(mapping)

        self.assertEqual(result["status"], "error")
        self.assertIn("Unexpected error: Unexpected error", result["message"])
        self.assertEqual(self.mock_s3_client.head_object.call_count, self.sample_s3_config.retry_attempts)

    def test_upload_metadata_csv_success(self) -> None:
        """Test successful metadata CSV upload."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        with patch.object(processor, "upload_data_as_csv") as mock_upload:
            mock_upload.return_value = {"status": "success", "key": "test-key"}

            result = processor.upload_metadata_csv(self.sample_query_results)

            mock_upload.assert_called_once_with(
                data=self.sample_query_results,
                fieldnames=list(self.sample_query_results[0].keys()),
                filename_prefix="metadata",
                subfolder="attachment_manifest",
                record_count_key="records_count",
            )

            self.assertEqual(result["status"], "success")

    def test_upload_metadata_csv_empty_results(self) -> None:
        """Test metadata CSV upload with empty results."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        result = processor.upload_metadata_csv([])

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "No query results to upload")

    def test_copy_single_file_copy_operation_fails(self) -> None:
        """Test single file copy when copy operation fails."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        self.mock_s3_client.head_object.return_value = {"ContentLength": 1024}
        error_response = {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}
        self.mock_s3_client.copy_object.side_effect = ClientError(error_response, "CopyObject")

        mapping = {"filename": "test_file.pdf", "output_filename": "renamed_file.pdf"}

        result = processor._copy_single_file(mapping)

        self.assertEqual(result["status"], "error")
        self.assertIn("AWS error (AccessDenied)", result["message"])

    def test_get_agency_folder_inherited(self) -> None:
        """Test that S3FileProcessor correctly inherits _get_agency_folder method."""
        processor = S3FileProcessor(self.sample_s3_config, self.mock_s3_client)

        agency_folder = processor._get_agency_folder()

        self.assertEqual(agency_folder, self.sample_s3_config.agency_s3_slug)


if __name__ == "__main__":
    import unittest
    unittest.main()
