import importlib.util
import unittest

from monitoring.services.validation import extract_schema_columns

PANDAS_AVAILABLE = importlib.util.find_spec("pandas") is not None
if PANDAS_AVAILABLE:
    import pandas as pd


class IngestionHelpersTest(unittest.TestCase):
    def test_extract_schema_columns(self):
        schema = {
            "strict": True,
            "columns": [
                {"name": "id", "required": True},
                {"name": "value", "unique": True},
            ],
        }
        columns, strict_mode = extract_schema_columns(schema)

        self.assertEqual(columns, ["id", "value"])
        self.assertTrue(strict_mode)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is not installed")
    def test_validate_bounds(self):
        from monitoring.services.validation import validate_bounds

        schema_columns = [
            {"name": "age", "min": 0, "max": 120},
            {"name": "score", "min": 50},
        ]
        dataframe = pd.DataFrame({"age": [10, 200], "score": [49, 100]})

        failures = validate_bounds(schema_columns, dataframe)

        self.assertEqual(
            failures,
            [
                {"column": "age", "issue": "above_max", "max": 120},
                {"column": "score", "issue": "below_min", "min": 50},
            ],
        )
