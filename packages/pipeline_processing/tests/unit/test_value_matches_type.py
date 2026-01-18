"""Unit tests for DataProfiler._value_matches_type helpers.

These tests exercise the type-matching logic (string/int/float/bool) including
SQL-type aliases added to the profiler.
"""
import unittest
from pipeline_processing.processors.profiler import DataProfiler


class ValueMatchesTypeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profiler = DataProfiler()

    def test_string_types(self) -> None:
        for t in ("string", "str", "text", "varchar"):
            ok, _ = self.profiler._value_matches_type("abc", t)
            self.assertTrue(ok, msg=f"Expected 'abc' to match {t}")
            ok, _ = self.profiler._value_matches_type(123, t)
            self.assertFalse(ok, msg=f"Expected integer 123 NOT to match {t}")

    def test_integer_types(self) -> None:
        for t in ("integer", "int", "int4", "int8", "bigint"):
            ok, _ = self.profiler._value_matches_type(5, t)
            self.assertTrue(ok, msg=f"Expected 5 to match {t}")
            ok, _ = self.profiler._value_matches_type("10", t)
            self.assertTrue(ok, msg=f"Expected '10' to parse as {t}")
            ok, _ = self.profiler._value_matches_type(True, t)
            self.assertFalse(ok, msg=f"Expected boolean True NOT to match integer {t}")
            ok, _ = self.profiler._value_matches_type("x", t)
            self.assertFalse(ok, msg=f"Expected 'x' NOT to parse as integer {t}")

    def test_float_types(self) -> None:
        for t in ("float", "number", "decimal", "double", "real", "numeric"):
            ok, _ = self.profiler._value_matches_type(3.14, t)
            self.assertTrue(ok, msg=f"Expected 3.14 to match {t}")
            ok, _ = self.profiler._value_matches_type("2.5", t)
            self.assertTrue(ok, msg=f"Expected '2.5' to parse as {t}")
            ok, _ = self.profiler._value_matches_type("not", t)
            self.assertFalse(ok, msg=f"Expected 'not' NOT to parse as {t}")

    def test_boolean_types(self) -> None:
        for t in ("boolean", "bool", "bit"):
            ok, _ = self.profiler._value_matches_type(True, t)
            self.assertTrue(ok, msg=f"Expected True to match {t}")
            ok, _ = self.profiler._value_matches_type("true", t)
            self.assertTrue(ok, msg=f"Expected 'true' to match {t}")
            ok, _ = self.profiler._value_matches_type("False", t)
            self.assertTrue(ok, msg=f"Expected 'False' to match {t}")
            ok, _ = self.profiler._value_matches_type("yes", t)
            self.assertFalse(ok, msg=f"Expected 'yes' NOT to match boolean {t}")


if __name__ == "__main__":
    unittest.main()
