"""Tests for the data quality job entrypoint."""
import io
import unittest
from contextlib import redirect_stdout
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from file_processing.jobs import data_quality_job


class DataQualityJobTest(unittest.TestCase):
    """Unit tests for the data quality job CLI entrypoint."""

    @patch("file_processing.jobs.data_quality_job.DataQualityProcessor")
    def test_entrypoint_success(self, mock_processor_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.run_checks.return_value = {
            "status": "success",
            "message": "ok",
            "metrics": {"agency_id": 7, "total_files": 1, "forms": 1, "user_documents": 0, "missing_output_filenames": 0},
            "issues": [],
        }
        mock_processor_cls.return_value = mock_instance

        with io.StringIO() as buf, redirect_stdout(buf):
            exit_code = data_quality_job.entrypoint(["--agency-id", "7"])
            output = buf.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("ok", output)
        mock_instance.run_checks.assert_called_once_with(7)

    @patch("file_processing.jobs.data_quality_job.DataQualityProcessor")
    def test_entrypoint_error_exit_code(self, mock_processor_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.run_checks.return_value = {
            "status": "error",
            "message": "boom",
            "metrics": {},
            "issues": [],
        }
        mock_processor_cls.return_value = mock_instance

        with io.StringIO() as buf, redirect_stdout(buf):
            exit_code = data_quality_job.entrypoint(["--agency-id", "5"])

        self.assertEqual(exit_code, 1)
        mock_instance.run_checks.assert_called_once_with(5)


if __name__ == "__main__":
    unittest.main()
