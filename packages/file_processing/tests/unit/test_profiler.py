import unittest
from typing import Any, Dict, List

from file_processing.processors.profiler import DataProfiler
from file_processing.models.quality import ProfilePayload, SampleData


class DataProfilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profiler = DataProfiler()

    def test_statistical_summary_structure(self) -> None:
        rows: List[Dict[str, Any]] = [
            {"age": 20, "salary": 50000, "race": "A"},
            {"age": 30, "salary": 70000, "race": "B"},
            {"age": 10, "salary": 40000, "race": "A"},
            {"age": 20, "salary": 50000, "race": "C"},
        ]
        columns = ["age", "salary", "race"]

        profile = self.profiler.generate_profile(rows, columns)
        summary = profile.statistical_summary

        self.assertIsInstance(summary, list)
        self.assertGreaterEqual(len(summary), 2)

        age_summary = next(item for item in summary if item["column"] == "age")
        self.assertIn("mean", age_summary)
        self.assertIn("median", age_summary)
        self.assertIn("stdDev", age_summary)
        self.assertIn("outlierValues", age_summary)
        self.assertIsInstance(age_summary["mean"], float)
        self.assertEqual(age_summary["count"], 4)

    def test_completeness_overview(self) -> None:
        rows = [
            {"a": 1, "b": None},
            {"a": 2, "b": ""},
            {"a": 3, "b": "x"},
        ]
        columns = ["a", "b"]

        profile = self.profiler.generate_profile(rows, columns)
        completeness = profile.completeness_overview

        self.assertEqual(completeness["totalRows"], 3)
        self.assertEqual(completeness["completeRows"], 1)
        self.assertTrue(any(col["column"] == "b" for col in completeness["columnsWithNulls"]))

    def test_value_distributions_shape(self) -> None:
        rows = [
            {"cat": "X"},
            {"cat": "Y"},
            {"cat": "X"},
            {"cat": "Z"},
        ]
        columns = ["cat"]

        profile = self.profiler.generate_profile(rows, columns)
        distributions = profile.value_distributions
        self.assertIsInstance(distributions, list)
        self.assertEqual(distributions[0]["column"], "cat")
        self.assertIsInstance(distributions[0]["histogram"], list)
        self.assertGreater(len(distributions[0]["histogram"]), 0)

    def test_uniqueness_overview_includes_cardinality(self) -> None:
        rows = [
            {"id": 1},
            {"id": 1},
            {"id": 2},
        ]
        columns = ["id"]

        profile = self.profiler.generate_profile(rows, columns)
        uniq = profile.uniqueness_overview
        self.assertEqual(uniq["totalRows"], 3)
        self.assertEqual(uniq["duplicateRows"], 1)
        self.assertEqual(len(uniq["columns"]), 1)
        self.assertIn("cardinality", uniq["columns"][0])

    def test_type_format_issues_detected(self) -> None:
        rows = [
            {"age": "not-a-number"},
            {"age": "10"},
        ]
        columns = ["age"]
        schema = {"columns": [{"name": "age", "type": "integer"}]}

        profile = self.profiler.generate_profile(rows, columns, schema)
        issues = profile.type_format_issues
        self.assertGreaterEqual(len(issues), 1)
        self.assertEqual(issues[0]["column"], "age")
        self.assertIn("invalidCount", issues[0])

    def test_bounds_anomalies(self) -> None:
        rows = [
            {"salary": 10},
            {"salary": 200},
            {"salary": 500},
        ]
        columns = ["salary"]
        schema = {"columns": [{"name": "salary", "min": 50, "max": 300}]}

        profile = self.profiler.generate_profile(rows, columns, schema)
        anomalies = profile.bounds_anomalies
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["column"], "salary")
        self.assertGreater(anomalies[0]["outliersCount"], 0)

    def test_sample_rows_capped(self) -> None:
        rows = [{"a": i} for i in range(50)]
        columns = ["a"]

        profile = self.profiler.generate_profile(rows, columns)
        self.assertIsNotNone(profile.sample_data)
        self.assertLessEqual(len(profile.sample_data.rows), 20)


class ProfilePayloadNormalizationTest(unittest.TestCase):
    def test_value_distributions_dict_and_list(self) -> None:
        payload = ProfilePayload(
            statistical_summary=[{"column": "a", "mean": 1.0}],
            value_distributions={
                "colA": [{"bin": "x", "count": 3}, {"bin": "y", "count": 1}]
            },
        )
        out = payload.to_dict()
        self.assertIsInstance(out["valueDistributions"], list)
        self.assertEqual(out["valueDistributions"][0]["column"], "colA")

        payload_list = ProfilePayload(
            statistical_summary=[{"column": "a", "mean": 1.0}],
            value_distributions=[{"column": "colB", "histogram": [{"bin": "z", "count": 2}]}],
        )
        out_list = payload_list.to_dict()
        self.assertEqual(out_list["valueDistributions"][0]["column"], "colB")

    def test_statistical_summary_dict_normalized(self) -> None:
        payload = ProfilePayload(
            statistical_summary={
                "a": {"column": "a", "mean": 1},
                "b": {"column": "b", "mean": 2},
            },
        )
        out = payload.to_dict()
        self.assertIsInstance(out["statisticalSummary"], list)
        self.assertEqual(len(out["statisticalSummary"]), 2)


if __name__ == "__main__":
    unittest.main()
