"""Unit tests for the S3Event model."""
import unittest
from datetime import date, datetime

from pipeline_processing.models.events import S3Event, ParsedS3Key


class S3EventParseKeyTest(unittest.TestCase):
    """Tests for S3Event.parse_key() method."""

    def test_parse_from_client_layout(self) -> None:
        """Test parsing legacy from_client layout with last_modified override."""
        event = S3Event(
            bucket="ignored",
            key="from_client/nm_albuquerque/Officer_detail.csv",
            last_modified=datetime(2026, 1, 5, 12, 0, 0),
        )

        parsed = event.parse_key()

        self.assertEqual(parsed.agency_slug, "nm_albuquerque")
        self.assertEqual(parsed.file_name, "Officer_detail.csv")
        self.assertEqual(parsed.run_date, date(2026, 1, 5))
        self.assertEqual(parsed.run_hour, 12)
        self.assertEqual(parsed.file_format, "csv")

    def test_parse_valid_key(self) -> None:
        """Test parsing a valid S3 key."""
        event = S3Event(
            bucket="my-bucket",
            key="agency/tenant-a/files/daily-report/2026-01-04/12/data.csv",
        )

        parsed = event.parse_key()

        self.assertEqual(parsed.agency_slug, "tenant-a")
        self.assertEqual(parsed.file_name, "daily-report")
        self.assertEqual(parsed.run_date, date(2026, 1, 4))
        self.assertEqual(parsed.run_hour, 12)
        self.assertEqual(parsed.file_format, "csv")

    def test_parse_jsonl_format(self) -> None:
        """Test detecting JSONL format from extension."""
        event = S3Event(
            bucket="my-bucket",
            key="agency/test-agency/files/events/2026-01-04/08/data.jsonl",
        )

        parsed = event.parse_key()

        self.assertEqual(parsed.file_format, "jsonl")

    def test_parse_parquet_format(self) -> None:
        """Test detecting Parquet format from extension."""
        event = S3Event(
            bucket="my-bucket",
            key="agency/prod-agency/files/large-data/2026-01-04/00/export.parquet",
        )

        parsed = event.parse_key()

        self.assertEqual(parsed.file_format, "parquet")

    def test_parse_invalid_key_too_short(self) -> None:
        """Test that short keys raise ValueError."""
        event = S3Event(bucket="bucket", key="short/key")

        with self.assertRaises(ValueError) as ctx:
            event.parse_key()

        self.assertIn("does not match expected format", str(ctx.exception))

    def test_parse_invalid_key_wrong_structure(self) -> None:
        """Test that incorrectly structured keys raise ValueError."""
        event = S3Event(
            bucket="bucket",
            key="wrong/tenant/structure/file/2026-01-04/12/data.csv",
        )

        with self.assertRaises(ValueError) as ctx:
            event.parse_key()

        self.assertIn("does not match expected format", str(ctx.exception))

    def test_parse_invalid_date(self) -> None:
        """Test that invalid dates raise ValueError."""
        event = S3Event(
            bucket="bucket",
            key="agency/tenant/files/file/not-a-date/12/data.csv",
        )

        with self.assertRaises(ValueError) as ctx:
            event.parse_key()

        self.assertIn("Invalid date", str(ctx.exception))

    def test_parse_invalid_hour(self) -> None:
        """Test that invalid hours raise ValueError."""
        event = S3Event(
            bucket="bucket",
            key="agency/tenant/files/file/2026-01-04/25/data.csv",
        )

        with self.assertRaises(ValueError) as ctx:
            event.parse_key()

        self.assertIn("Invalid hour", str(ctx.exception))


class ParsedS3KeyTest(unittest.TestCase):
    """Tests for ParsedS3Key."""

    def test_run_date_str(self) -> None:
        """Test run_date_str property."""
        parsed = ParsedS3Key(
            agency_slug="test",
            file_name="file",
            run_date=date(2026, 1, 15),
            run_hour=8,
        )

        self.assertEqual(parsed.run_date_str, "2026-01-15")


if __name__ == "__main__":
    unittest.main()
