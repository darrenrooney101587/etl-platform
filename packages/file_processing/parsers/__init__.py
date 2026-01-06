"""File parsers for the data quality pipeline.

This module provides a pluggable parser registry supporting CSV, JSONL, and Parquet formats.
"""
from __future__ import annotations

from file_processing.parsers.registry import ParserRegistry, get_parser
from file_processing.parsers.base import BaseParser, ParseResult
from file_processing.parsers.csv_parser import CsvParser
from file_processing.parsers.jsonl_parser import JsonlParser
from file_processing.parsers.parquet_parser import ParquetParser

__all__ = [
    "BaseParser",
    "CsvParser",
    "JsonlParser",
    "ParquetParser",
    "ParserRegistry",
    "ParseResult",
    "get_parser",
]
