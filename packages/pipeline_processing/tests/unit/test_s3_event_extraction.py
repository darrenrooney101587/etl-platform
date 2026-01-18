"""Unit tests for AWS event payload extraction in s3_data_quality_job."""
import unittest

from pipeline_processing.jobs.s3_data_quality_job import _extract_s3_events


class S3EventExtractionTest(unittest.TestCase):
    """Tests for extracting S3 events from AWS-style payloads."""

    def test_extract_direct_payload(self) -> None:
        events = _extract_s3_events({"bucket": "b", "key": "k"})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].bucket, "b")
        self.assertEqual(events[0].key, "k")

    def test_extract_s3_records_payload(self) -> None:
        payload = {
            "Records": [
                {"s3": {"bucket": {"name": "b"}, "object": {"key": "k"}}},
            ]
        }
        events = _extract_s3_events(payload)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].bucket, "b")
        self.assertEqual(events[0].key, "k")

    def test_extract_sns_wrapped_payload(self) -> None:
        payload = {
            "Records": [
                {
                    "Sns": {
                        "Message": '{"Records": [{"s3": {"bucket": {"name": "b"}, "object": {"key": "k"}}}]}'
                    }
                }
            ]
        }
        events = _extract_s3_events(payload)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].bucket, "b")
        self.assertEqual(events[0].key, "k")


if __name__ == "__main__":
    unittest.main()
