"""Unit tests for DataProfiler initialization and utility methods.

Ensures complete coverage for DataProfiler methods not fully exercies by functional tests.
"""
import unittest
from pipeline_processing.processors.profiler import DataProfiler


class DataProfilerMethodsTest(unittest.TestCase):
    def test_init_defaults(self) -> None:
        """Test default initialization values."""
        profiler = DataProfiler()
        self.assertEqual(profiler._max_sample_rows, 20)
        self.assertEqual(profiler._max_distribution_items, 25)

    def test_init_custom(self) -> None:
        """Test custom initialization values."""
        profiler = DataProfiler(max_sample_rows=100, max_distribution_items=50)
        self.assertEqual(profiler._max_sample_rows, 100)
        self.assertEqual(profiler._max_distribution_items, 50)

    def test_is_null(self) -> None:
        """Test null detection logic."""
        p = DataProfiler()

        # Null values
        self.assertTrue(p._is_null(None))
        self.assertTrue(p._is_null(""))
        self.assertTrue(p._is_null("   "))
        self.assertTrue(p._is_null("null"))
        self.assertTrue(p._is_null("NULL"))
        self.assertTrue(p._is_null("Null"))

        # Non-null values
        self.assertFalse(p._is_null("value"))
        self.assertFalse(p._is_null(0))
        self.assertFalse(p._is_null(False))
        self.assertFalse(p._is_null("0"))
        self.assertFalse(p._is_null("None"))  # Only "null" is matched, not "None" text

    def test_generate_profile_empty(self) -> None:
        """Test generate_profile returns empty profile on no input."""
        p = DataProfiler()
        # Empty rows
        profile = p.generate_profile([], ["col"])
        self.assertEqual(profile.statistical_summary, [])

        # Empty columns
        profile = p.generate_profile([{"a": 1}], [])
        self.assertEqual(profile.statistical_summary, [])


if __name__ == "__main__":
    unittest.main()
