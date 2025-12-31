import sys
from unittest.mock import MagicMock

# Mock external dependencies that might be missing in the environment
for module in ['django', 'django.db', 'django.conf', 'django_core', 'django_core.settings', 'django_core.settings.base', 'botocore', 'botocore.exceptions', 'boto3']:
    if module not in sys.modules:
        sys.modules[module] = MagicMock()

import unittest
from unittest.mock import MagicMock, patch
from data_pipeline.processors.s3_file_processor import S3FileProcessor
from data_pipeline.processors.employment_history_processor import EmploymentHistoryProcessor
from data_pipeline.config.config import S3Config, EmploymentHistoryConfig

class TestS3FileProcessor(unittest.TestCase):
    def setUp(self):
        self.config = S3Config(
            source_bucket="source-bucket",
            destination_bucket="dest-bucket",
            agency_s3_slug="agency-slug",
            agency_id=123
        )
        self.mock_s3_client = MagicMock()

    def test_initialization(self):
        processor = S3FileProcessor(self.config, self.mock_s3_client)
        self.assertEqual(processor.config, self.config)
        self.assertEqual(processor.s3_client, self.mock_s3_client)

    def test_set_progress_callback(self):
        processor = S3FileProcessor(self.config, self.mock_s3_client)
        callback = MagicMock()
        processor.set_progress_callback(callback)
        self.assertEqual(processor._progress_callback, callback)

    def test_process_files_success(self):
        processor = S3FileProcessor(self.config, self.mock_s3_client)

        # Mock head_object response
        self.mock_s3_client.head_object.return_value = {'ContentLength': 1024}

        # Mock copy_object response
        self.mock_s3_client.copy_object.return_value = {}

        file_mappings = [
            {'filename': 'source.txt', 'output_filename': 'dest.txt'}
        ]

        results = processor.process_files(file_mappings)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['status'], 'success')
        self.assertEqual(results[0]['source_key'], 'source.txt')

        # Verify calls
        self.mock_s3_client.head_object.assert_called_with(
            Bucket=self.config.source_bucket,
            Key='source.txt'
        )
        # Note: destination_prefix defaults to "/downloads/"
        # agency_s3_slug is "agency-slug"
        # So key should be "agency-slug/downloads/dest.txt"
        self.mock_s3_client.copy_object.assert_called_with(
            CopySource={'Bucket': self.config.source_bucket, 'Key': 'source.txt'},
            Bucket=self.config.destination_bucket,
            Key='agency-slug/downloads/dest.txt'
        )

class TestEmploymentHistoryProcessor(unittest.TestCase):
    def setUp(self):
        self.config = EmploymentHistoryConfig(
            destination_bucket="dest-bucket",
            agency_s3_slug="agency-slug",
            agency_id=123
        )
        self.mock_s3_client = MagicMock()

    @patch('data_pipeline.processors.employment_history_processor.client.DatabaseClient')
    def test_fetch_data(self, MockDatabaseClient):
        mock_db_client = MockDatabaseClient.return_value
        mock_db_client.get_organization_employment_history.return_value = [{'id': 1, 'name': 'Test'}]

        processor = EmploymentHistoryProcessor(self.config, self.mock_s3_client)
        data = processor.fetch_data()

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], 'Test')
        mock_db_client.get_organization_employment_history.assert_called_once_with(123)

if __name__ == '__main__':
    unittest.main()
