"""Tests for DataQualityProcessor."""
import unittest
from typing import Any, Dict, List

from file_processing.processors.data_quality_processor import DataQualityProcessor


class FakeRepository:
    """Fake repository that returns predetermined rows."""

    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows

    def get_attachment_files_for_s3_processing(self, agency_id: int) -> List[Dict[str, Any]]:
        return self._rows


class FailingRepository:
    """Fake repository that raises to simulate DB errors."""

    def get_attachment_files_for_s3_processing(self, agency_id: int) -> List[Dict[str, Any]]:
        raise RuntimeError("db unavailable")


class DataQualityProcessorTest(unittest.TestCase):
    """Unit tests for DataQualityProcessor."""

    def test_run_checks_success(self) -> None:
        repo = FakeRepository(
            [
                {"filename": "a.pdf", "output_filename": "1_a.pdf", "attachable_type": "Form"},
                {"filename": "b.pdf", "output_filename": "2_b.pdf", "attachable_type": "UserDocument"},
            ]
        )
        processor = DataQualityProcessor(repo)

        result = processor.run_checks(agency_id=42)

        self.assertEqual(result["status"], "success")
        metrics = result["metrics"]
        self.assertEqual(metrics["total_files"], 2)
        self.assertEqual(metrics["forms"], 1)
        self.assertEqual(metrics["user_documents"], 1)
        self.assertEqual(metrics["missing_output_filenames"], 0)
        self.assertFalse(result["issues"])

    def test_run_checks_with_missing_output(self) -> None:
        repo = FakeRepository(
            [
                {"filename": "missing.pdf", "output_filename": "", "attachable_type": "Form"},
                {"filename": "ok.pdf", "output_filename": "ok.pdf", "attachable_type": "UserDocument"},
            ]
        )
        processor = DataQualityProcessor(repo)

        result = processor.run_checks(agency_id=99)

        self.assertEqual(result["status"], "warning")
        metrics = result["metrics"]
        self.assertEqual(metrics["missing_output_filenames"], 1)
        self.assertEqual(len(result["issues"]), 1)
        self.assertEqual(result["issues"][0]["type"], "missing_output_filename")

    def test_run_checks_handles_errors(self) -> None:
        processor = DataQualityProcessor(FailingRepository())

        result = processor.run_checks(agency_id=1)

        self.assertEqual(result["status"], "error")
        self.assertIn("Failed to read attachment data", result["message"])


if __name__ == "__main__":
    unittest.main()
