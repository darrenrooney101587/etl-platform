import unittest
from unittest.mock import MagicMock

from file_processing.processors.s3_data_quality_processor import S3DataQualityProcessor, S3DataQualityProcessorConfig
from file_processing.models.events import S3Event
from file_processing.parsers import ParseResult


class FakeRepo:
    def get_monitoring_file(self, agency_slug, file_name, s3_key=None):
        class MF:
            id = 1
            is_suppressed = False
            schema_definition_id = None
        return MF()


class FakeS3Client:
    def __init__(self, raise_nosuchkey=False):
        self.s3_client = MagicMock()
        if raise_nosuchkey:
            from botocore.exceptions import ClientError

            def _get_object(Bucket, Key):
                raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "Not found"}}, "GetObject")

            self.s3_client.get_object.side_effect = _get_object
        else:
            def _get_object(Bucket, Key):
                return {"Body": b"col1,col2\n1,2\n"}

            self.s3_client.get_object.side_effect = _get_object


class TestS3NoSuchKeyLogging(unittest.TestCase):
    def test_nosuchkey_returns_parse_result_with_error_message(self):
        repo = FakeRepo()
        s3_client = FakeS3Client(raise_nosuchkey=True)
        proc = S3DataQualityProcessor(repository=repo, s3_client=s3_client, config=S3DataQualityProcessorConfig())

        event = S3Event(bucket="etl-ba-research-client-etl", key="missing.csv")
        result = proc._download_and_parse(event, file_format="csv")

        self.assertFalse(result.success)
        self.assertIn("NoSuchKey:", result.error_message)


if __name__ == "__main__":
    unittest.main()
