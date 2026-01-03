"""Unit tests for etl_core S3Client (migrated from data_pipeline tests).

These tests were adapted to import from etl_core and to patch the correct
module paths.
"""
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from botocore.exceptions import NoCredentialsError

from etl_core.config.config import S3Config
from etl_core.config.config import EmploymentHistoryConfig
from etl_core.s3.client import S3Client


class TestBaseS3Client(unittest.TestCase):
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

        self.sample_employment_config = EmploymentHistoryConfig(
            agency_id=123,
            destination_bucket="test-destination-bucket",
            agency_s3_slug="test-agency-slug",
            destination_prefix="/downloads/",
            aws_access_key_id="test_access_key",
            aws_secret_access_key="test_secret_key",
            aws_region="us-gov-west-1",
        )

    def test_init_with_s3_client(self) -> None:
        client = S3Client(self.sample_s3_config, self.mock_s3_client)

        self.assertEqual(client.config, self.sample_s3_config)
        self.assertIs(client.s3_client, self.mock_s3_client)

    def test_init_without_s3_client(self) -> None:
        with patch.object(S3Client, "_initialize_s3_client") as mock_init:
            mock_client = Mock()
            mock_init.return_value = mock_client

            client = S3Client(self.sample_s3_config)

            self.assertEqual(client.config, self.sample_s3_config)
            self.assertIs(client.s3_client, mock_client)
            mock_init.assert_called_once()

    @patch("etl_core.s3.client.boto3")
    def test_initialize_s3_client_with_credentials(self, mock_boto3: Mock) -> None:
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        client = S3Client(self.sample_s3_config)

        mock_boto3.client.assert_called_once_with(
            "s3",
            aws_access_key_id=self.sample_s3_config.aws_access_key_id,
            aws_secret_access_key=self.sample_s3_config.aws_secret_access_key,
            region_name=self.sample_s3_config.aws_region,
        )
        self.assertIs(client.s3_client, mock_client)

    @patch("etl_core.s3.client.boto3")
    def test_initialize_s3_client_without_credentials(self, mock_boto3: Mock) -> None:
        config = S3Config(
            source_bucket="test-source",
            destination_bucket="test-dest",
            agency_s3_slug="test-agency",
            aws_access_key_id=None,
            aws_secret_access_key=None,
        )

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        client = S3Client(config)

        mock_boto3.client.assert_called_once_with("s3", region_name=config.aws_region)
        self.assertIs(client.s3_client, mock_client)

    @patch("etl_core.s3.client.boto3")
    def test_initialize_s3_client_no_credentials_error(self, mock_boto3: Mock) -> None:
        config = S3Config(
            source_bucket="test-source",
            destination_bucket="test-dest",
            agency_s3_slug="test-agency",
        )

        mock_boto3.client.side_effect = NoCredentialsError()

        with self.assertRaises(NoCredentialsError):
            S3Client(config)

    def test_get_agency_folder_with_slug(self) -> None:
        client = S3Client(self.sample_s3_config, self.mock_s3_client)

        result = client._get_agency_folder()

        self.assertEqual(result, self.sample_s3_config.agency_s3_slug)

    def test_get_agency_folder_with_id_no_slug(self) -> None:
        config = S3Config(
            source_bucket="test-source",
            destination_bucket="test-dest",
            agency_s3_slug="",
            agency_id=456,
        )

        client = S3Client(config, self.mock_s3_client)

        result = client._get_agency_folder()

        self.assertEqual(result, "agency-456")

    def test_get_agency_folder_no_slug_no_id(self) -> None:
        config = S3Config(
            source_bucket="test-source",
            destination_bucket="test-dest",
            agency_s3_slug="",
            agency_id=None,
        )

        client = S3Client(config, self.mock_s3_client)

        result = client._get_agency_folder()

        self.assertEqual(result, "unknown-agency")

    def test_upload_csv_to_s3_success(self) -> None:
        client = S3Client(self.sample_s3_config, self.mock_s3_client)
        csv_content = "header1,header2\nvalue1,value2"
        filename = "test.csv"
        subfolder = "test_folder"

        result = client.upload_csv_to_s3(csv_content, filename, subfolder)

        expected_key = f"{self.sample_s3_config.agency_s3_slug}{self.sample_s3_config.destination_prefix.rstrip('/')}/{subfolder}/{filename}"

        self.mock_s3_client.put_object.assert_called_once_with(
            Bucket=self.sample_s3_config.destination_bucket,
            Key=expected_key,
            Body=csv_content.encode("utf-8"),
            ContentType="text/csv",
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["s3_key"], expected_key)
        self.assertEqual(result["filename"], filename)
        self.assertIn("file_size", result)

    def test_upload_csv_to_s3_empty_content(self) -> None:
        client = S3Client(self.sample_s3_config, self.mock_s3_client)

        result = client.upload_csv_to_s3("", "test.csv", "")

        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["message"], "No data to upload")
        self.mock_s3_client.put_object.assert_not_called()

    def test_upload_csv_to_s3_no_subfolder(self) -> None:
        client = S3Client(self.sample_s3_config, self.mock_s3_client)
        csv_content = "header1,header2\nvalue1,value2"
        filename = "test.csv"

        result = client.upload_csv_to_s3(csv_content, filename, "")

        expected_key = f"{self.sample_s3_config.agency_s3_slug}{self.sample_s3_config.destination_prefix.rstrip('/')}/{filename}"

        self.mock_s3_client.put_object.assert_called_once_with(
            Bucket=self.sample_s3_config.destination_bucket,
            Key=expected_key,
            Body=csv_content.encode("utf-8"),
            ContentType="text/csv",
        )

    def test_upload_csv_to_s3_exception(self) -> None:
        client = S3Client(self.sample_s3_config, self.mock_s3_client)
        self.mock_s3_client.put_object.side_effect = Exception("Upload failed")

        result = client.upload_csv_to_s3("test content", "test.csv", "")

        self.assertEqual(result["status"], "error")
        self.assertIn("Upload failed", result["message"])

    def test_upload_data_as_csv_success(self) -> None:
        client = S3Client(self.sample_s3_config, self.mock_s3_client)
        data = [
            {"name": "John", "age": 30, "date": datetime(2023, 1, 1)},
            {"name": "Jane", "age": 25, "date": datetime(2023, 1, 2)},
        ]
        fieldnames = ["name", "age", "date"]

        with patch.object(client, "upload_csv_to_s3") as mock_upload:
            mock_upload.return_value = {"status": "success", "key": "test-key"}

            result = client.upload_data_as_csv(
                data, fieldnames, "test_prefix", "test_subfolder", "record_count"
            )

            self.assertTrue(mock_upload.called)
            call_args = mock_upload.call_args
            csv_content = call_args[0][0]
            filename = call_args[0][1]
            subfolder = call_args[0][2]

            self.assertIn("name,age,date", csv_content)
            self.assertIn("John,30,2023-01-01T00:00:00", csv_content)
            self.assertIn("Jane,25,2023-01-02T00:00:00", csv_content)

            self.assertTrue(filename.startswith("test_prefix_"))
            self.assertTrue(filename.endswith(".csv"))

            self.assertEqual(subfolder, "test_subfolder")

    def test_upload_data_as_csv_empty_data(self) -> None:
        client = S3Client(self.sample_s3_config, self.mock_s3_client)

        result = client.upload_data_as_csv([], ["name"], "test_prefix")

        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["message"], "No data to upload")

    def test_upload_data_as_csv_with_record_count(self) -> None:
        client = S3Client(self.sample_s3_config, self.mock_s3_client)
        data = [{"name": "John"}, {"name": "Jane"}]

        with patch.object(client, "upload_csv_to_s3") as mock_upload:
            mock_upload.return_value = {"status": "success"}

            result = client.upload_data_as_csv(
                data, ["name"], "test_prefix", record_count_key="count"
            )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["count"], 2)

    def test_upload_data_as_csv_exception(self) -> None:
        client = S3Client(self.sample_s3_config, self.mock_s3_client)
        data = [{"name": "John"}]

        with patch("etl_core.s3.client.csv.DictWriter") as mock_writer:
            mock_writer.side_effect = Exception("CSV error")

            result = client.upload_data_as_csv(data, ["name"], "test_prefix")

            self.assertEqual(result["status"], "error")
            self.assertIn("CSV error", result["message"])

    def test_employment_history_config_compatibility(self) -> None:
        client = S3Client(self.sample_employment_config, self.mock_s3_client)

        self.assertEqual(client.config, self.sample_employment_config)
        self.assertIs(client.s3_client, self.mock_s3_client)

        result = client._get_agency_folder()
        self.assertEqual(result, self.sample_employment_config.agency_s3_slug)


if __name__ == "__main__":
    unittest.main()
