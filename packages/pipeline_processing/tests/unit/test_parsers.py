"""Unit tests for the parser registry and parsers."""
import io
import unittest

from pipeline_processing.parsers import (
    CsvParser,
    JsonlParser,
    ParserRegistry,
    ParseResult,
    get_parser,
)


class CsvParserTest(unittest.TestCase):
    """Tests for CsvParser."""

    def test_parse_valid_csv(self) -> None:
        """Test parsing a valid CSV file."""
        csv_data = b"name,age,city\nAlice,30,NYC\nBob,25,LA"
        parser = CsvParser()

        result = parser.parse_bytes(csv_data)

        self.assertTrue(result.success)
        self.assertEqual(result.row_count, 2)
        self.assertEqual(result.columns, ["name", "age", "city"])
        self.assertEqual(result.rows[0]["name"], "Alice")
        self.assertEqual(result.rows[1]["city"], "LA")

    def test_parse_empty_csv(self) -> None:
        """Test parsing an empty CSV (header only)."""
        csv_data = b"name,age\n"
        parser = CsvParser()

        result = parser.parse_bytes(csv_data)

        self.assertTrue(result.success)
        self.assertEqual(result.row_count, 0)
        self.assertEqual(result.columns, ["name", "age"])

    def test_parse_csv_with_empty_values(self) -> None:
        """Test that empty values become None."""
        csv_data = b"name,value\nAlice,\nBob,123"
        parser = CsvParser()

        result = parser.parse_bytes(csv_data)

        self.assertTrue(result.success)
        self.assertIsNone(result.rows[0]["value"])
        self.assertEqual(result.rows[1]["value"], "123")

    def test_parse_invalid_encoding(self) -> None:
        """Test handling of invalid encoding."""
        invalid_bytes = b"\xff\xfe invalid utf-8"
        parser = CsvParser()

        result = parser.parse_bytes(invalid_bytes)

        self.assertFalse(result.success)
        self.assertIn("decode", result.error_message.lower())


class JsonlParserTest(unittest.TestCase):
    """Tests for JsonlParser."""

    def test_parse_valid_jsonl(self) -> None:
        """Test parsing valid JSONL."""
        jsonl_data = b'{"name": "Alice", "age": 30}\n{"name": "Bob", "age": 25}'
        parser = JsonlParser()

        result = parser.parse_bytes(jsonl_data)

        self.assertTrue(result.success)
        self.assertEqual(result.row_count, 2)
        self.assertIn("name", result.columns)
        self.assertIn("age", result.columns)
        self.assertEqual(result.rows[0]["name"], "Alice")

    def test_parse_jsonl_with_empty_lines(self) -> None:
        """Test that empty lines are skipped."""
        jsonl_data = b'{"a": 1}\n\n{"a": 2}\n'
        parser = JsonlParser()

        result = parser.parse_bytes(jsonl_data)

        self.assertTrue(result.success)
        self.assertEqual(result.row_count, 2)

    def test_parse_jsonl_with_errors(self) -> None:
        """Test handling of invalid JSON lines."""
        jsonl_data = b'{"valid": true}\nnot json\n{"also": "valid"}'
        parser = JsonlParser()

        result = parser.parse_bytes(jsonl_data)

        self.assertTrue(result.success)
        self.assertEqual(result.row_count, 2)
        self.assertGreater(len(result.warnings), 0)


class ParserRegistryTest(unittest.TestCase):
    """Tests for ParserRegistry."""

    def test_get_csv_parser(self) -> None:
        """Test getting CSV parser."""
        parser = get_parser("csv")

        self.assertIsNotNone(parser)
        self.assertEqual(parser.format_name, "csv")

    def test_get_jsonl_parser(self) -> None:
        """Test getting JSONL parser."""
        parser = get_parser("jsonl")

        self.assertIsNotNone(parser)
        self.assertEqual(parser.format_name, "jsonl")

    def test_get_parser_case_insensitive(self) -> None:
        """Test that parser lookup is case insensitive."""
        parser = get_parser("CSV")

        self.assertIsNotNone(parser)
        self.assertEqual(parser.format_name, "csv")

    def test_get_unknown_parser(self) -> None:
        """Test that unknown format returns None."""
        parser = get_parser("unknown_format")

        self.assertIsNone(parser)

    def test_registry_available_formats(self) -> None:
        """Test listing available formats."""
        registry = ParserRegistry.get_instance()
        formats = registry.available_formats

        self.assertIn("csv", formats)
        self.assertIn("jsonl", formats)
        self.assertIn("parquet", formats)


if __name__ == "__main__":
    unittest.main()
