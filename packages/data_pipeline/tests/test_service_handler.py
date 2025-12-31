import sys
from unittest.mock import MagicMock

# Mock external dependencies
for module in ['django', 'django.db', 'django.conf', 'django_core', 'django_core.settings', 'django_core.settings.base', 'botocore', 'botocore.exceptions', 'boto3']:
    if module not in sys.modules:
        sys.modules[module] = MagicMock()

import unittest
from unittest.mock import patch, MagicMock
from data_pipeline.service_handler import ServiceHandler

class TestServiceHandler(unittest.TestCase):
    @patch('data_pipeline.service_handler.DatabaseClient')
    def test_initialization(self, MockDatabaseClient):
        handler = ServiceHandler(
            source_bucket="source",
            destination_bucket="dest"
        )
        self.assertEqual(handler.source_bucket, "source")
        self.assertEqual(handler.destination_bucket, "dest")
        MockDatabaseClient.assert_called_with(db_alias='bms')

    @patch('data_pipeline.service_handler.create_employment_history_processor')
    @patch('data_pipeline.service_handler.DatabaseClient')
    def test_analyze_agency_data(self, MockDatabaseClient, mock_create_processor):
        mock_db = MockDatabaseClient.return_value
        mock_db.get_agency_s3_slug.return_value = "test-slug"
        mock_db.get_attachment_files_for_s3_processing.return_value = [
            {'attachable_type': 'Form', 'byte_size': 1024},
            {'attachable_type': 'UserDocument', 'byte_size': 2048}
        ]

        mock_processor = mock_create_processor.return_value
        mock_processor.fetch_data.return_value = [1, 2, 3]

        handler = ServiceHandler("source", "dest")
        result = handler.analyze_agency_data(123)

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['agency_id'], 123)
        self.assertEqual(result['agency_s3_slug'], 'test-slug')
        self.assertEqual(result['files']['total'], 2)
        self.assertEqual(result['files']['forms'], 1)
        self.assertEqual(result['files']['user_documents'], 1)
        self.assertEqual(result['employment_records'], 3)

        mock_db.get_agency_s3_slug.assert_called_with(123)
        mock_db.get_attachment_files_for_s3_processing.assert_called_with(123)
        mock_create_processor.assert_called()

if __name__ == '__main__':
    unittest.main()
