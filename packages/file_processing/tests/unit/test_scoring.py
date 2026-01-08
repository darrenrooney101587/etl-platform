"""Unit tests for data quality scoring logic."""
import unittest

from file_processing.models.quality import (
    DataQualityDeductions,
    DataQualityMetrics,
    DataQualityResult,
    MetricResult,
)


class DataQualityDeductionsTest(unittest.TestCase):
    """Tests for DataQualityDeductions."""

    def test_total_zero_deductions(self) -> None:
        """Test total with no deductions."""
        deductions = DataQualityDeductions()

        self.assertEqual(deductions.total(), 0.0)

    def test_total_all_deductions(self) -> None:
        """Test total with all deductions at max."""
        deductions = DataQualityDeductions(
            schema=40.0,
            format=35.0,
            completeness=20.0,
            bounds=15.0,
            uniqueness=10.0,
        )

        self.assertEqual(deductions.total(), 120.0)

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        deductions = DataQualityDeductions(
            schema=8.0,
            format=0.0,
            completeness=5.5,
            bounds=0.0,
            uniqueness=3.33,
        )

        result = deductions.to_dict()

        self.assertEqual(result["schema"], 8.0)
        self.assertEqual(result["format"], 0.0)
        self.assertEqual(result["completeness"], 5.5)
        self.assertEqual(result["bounds"], 0.0)
        self.assertEqual(result["uniqueness"], 3.33)


class DataQualityResultTest(unittest.TestCase):
    """Tests for DataQualityResult scoring logic."""

    def test_compute_score_no_deductions(self) -> None:
        """Test score computation with no deductions."""
        deductions = DataQualityDeductions()

        score = DataQualityResult.compute_score(deductions)

        self.assertEqual(score, 100)

    def test_compute_score_with_deductions(self) -> None:
        """Test score computation with partial deductions."""
        deductions = DataQualityDeductions(
            schema=8.0,
            completeness=5.0,
            uniqueness=10.0,
        )

        score = DataQualityResult.compute_score(deductions)

        self.assertEqual(score, 77)  # 100 - 23 = 77

    def test_compute_score_clamped_to_zero(self) -> None:
        """Test score is clamped to minimum 0."""
        deductions = DataQualityDeductions(
            schema=40.0,
            format=35.0,
            completeness=20.0,
            bounds=15.0,
            uniqueness=10.0,
        )

        score = DataQualityResult.compute_score(deductions)

        self.assertEqual(score, 0)

    def test_is_passed_above_threshold(self) -> None:
        """Test that score >= 80 passes."""
        self.assertTrue(DataQualityResult.is_passed(80))
        self.assertTrue(DataQualityResult.is_passed(100))

    def test_is_passed_below_threshold(self) -> None:
        """Test that score < 80 fails."""
        self.assertFalse(DataQualityResult.is_passed(79))
        self.assertFalse(DataQualityResult.is_passed(0))

    def test_fractional_deductions(self) -> None:
        """Test proportional deductions scenario.

        Example from instructions: if 1 of 5 schema fields failed,
        deduct 40 * 1/5 = 8 points.
        """
        deductions = DataQualityDeductions(schema=8.0)

        score = DataQualityResult.compute_score(deductions)

        self.assertEqual(score, 92)


class DataQualityMetricsTest(unittest.TestCase):
    """Tests for DataQualityMetrics."""

    def test_to_dict_format(self) -> None:
        """Test that to_dict produces correct JSON structure."""
        metrics = DataQualityMetrics(
            schema_validation=MetricResult(passed=True, details="OK"),
            format_parsing=MetricResult(passed=True, details="CSV parsed"),
            completeness=MetricResult(passed=False, details="3% nulls"),
            bounds_range=MetricResult(passed=True, details="In range"),
            uniqueness=MetricResult(passed=False, details="97% unique"),
        )

        result = metrics.to_dict()

        self.assertIn("schemaValidation", result)
        self.assertIn("formatParsing", result)
        self.assertIn("completeness", result)
        self.assertIn("boundsRange", result)
        self.assertIn("uniqueness", result)

        self.assertTrue(result["schemaValidation"]["passed"])
        self.assertFalse(result["completeness"]["passed"])
        self.assertEqual(result["completeness"]["details"], "3% nulls")


class SampleDataTest(unittest.TestCase):
    """Tests for SampleData."""

    def test_to_dict(self) -> None:
        from file_processing.models.quality import SampleData

        sd = SampleData(columns=["a", "b"], rows=[[1, 2], [3, 4]])
        d = sd.to_dict()
        self.assertEqual(d["columns"], ["a", "b"])
        self.assertEqual(len(d["rows"]), 2)
        self.assertEqual(d["rows"][0], [1, 2])


class FullDataQualityResultTest(unittest.TestCase):
    """Tests for DataQualityResult serialization."""

    def test_to_dict(self) -> None:
        deductions = DataQualityDeductions()
        metrics = DataQualityMetrics()

        res = DataQualityResult(
            score=95,
            passed=True,
            metrics=metrics,
            deductions=deductions,
            failed_validation_message="Some error",
            failed_validation_rules=[{"rule": "r1"}],
        )

        d = res.to_dict()
        self.assertEqual(d["score"], 95)
        self.assertEqual(d["passed"], True)
        self.assertIn("metrics", d)
        self.assertIn("deductions", d)
        self.assertEqual(d["failed_validation_message"], "Some error")
        self.assertEqual(d["failed_validation_rules"], [{"rule": "r1"}])
        self.assertIsNone(d["profile"])


if __name__ == "__main__":
    unittest.main()
