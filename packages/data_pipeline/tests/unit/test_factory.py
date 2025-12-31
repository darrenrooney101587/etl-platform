from packages.data_pipeline.config.factory import create_s3_processor, create_employment_history_processor
from packages.data_pipeline.processors.employment_history_processor import EmploymentHistoryProcessor
from packages.data_pipeline.processors.s3_file_processor import S3FileProcessor
from packages.data_pipeline.tests.unit.conftest import setup_mocks

setup_mocks()

import unittest

class TestFactory(unittest.TestCase):
    def test_create_s3_processor(self):
        processor = create_s3_processor(
            source_bucket="source",
            destination_bucket="dest",
            agency_s3_slug="slug",
            agency_id=123
        )
        self.assertIsInstance(processor, S3FileProcessor)
        self.assertEqual(processor.config.source_bucket, "source")
        self.assertEqual(processor.config.destination_bucket, "dest")
        self.assertEqual(processor.config.agency_s3_slug, "slug")
        self.assertEqual(processor.config.agency_id, 123)

    def test_create_employment_history_processor(self):
        processor = create_employment_history_processor(
            agency_id=123,
            destination_bucket="dest",
            agency_s3_slug="slug"
        )
        self.assertIsInstance(processor, EmploymentHistoryProcessor)
        self.assertEqual(processor.config.agency_id, 123)
        self.assertEqual(processor.config.destination_bucket, "dest")
        self.assertEqual(processor.config.agency_s3_slug, "slug")

if __name__ == "__main__":
    import unittest
    unittest.main()
