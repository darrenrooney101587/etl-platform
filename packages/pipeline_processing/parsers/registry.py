"""Parser registry for pluggable file format support."""
from __future__ import annotations

import logging
from typing import Dict, Optional, Type

from pipeline_processing.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class ParserRegistry:
    """Registry for file parsers.

    Provides a central place to register and retrieve parsers by format name.
    Default parsers for CSV, JSONL, and Parquet are registered automatically.
    """

    _instance: Optional["ParserRegistry"] = None
    _parsers: Dict[str, BaseParser]

    def __init__(self) -> None:
        """Initialize the registry with default parsers."""
        self._parsers = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the default parsers."""
        from pipeline_processing.parsers.csv_parser import CsvParser
        from pipeline_processing.parsers.jsonl_parser import JsonlParser
        from pipeline_processing.parsers.parquet_parser import ParquetParser

        self.register(CsvParser())
        self.register(JsonlParser())
        self.register(ParquetParser())

        # Register aliases
        self._parsers["json"] = self._parsers["jsonl"]

    @classmethod
    def get_instance(cls) -> "ParserRegistry":
        """Get the singleton instance of the registry.

        Returns:
            The global ParserRegistry instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, parser: BaseParser) -> None:
        """Register a parser for a format.

        Args:
            parser: The parser instance to register.
        """
        format_name = parser.format_name.lower()
        self._parsers[format_name] = parser
        logger.debug("Registered parser for format: %s", format_name)

    def get(self, format_name: str) -> Optional[BaseParser]:
        """Get a parser by format name.

        Args:
            format_name: The format name (e.g., 'csv', 'jsonl', 'parquet').

        Returns:
            The parser for the format, or None if not registered.
        """
        return self._parsers.get(format_name.lower())

    def get_for_extension(self, extension: str) -> Optional[BaseParser]:
        """Get a parser by file extension.

        Args:
            extension: The file extension (with or without leading dot).

        Returns:
            The parser for the extension, or None if not recognized.
        """
        ext = extension.lstrip(".").lower()

        extension_map = {
            "csv": "csv",
            "tsv": "csv",  # TSV uses CSV parser with tab delimiter
            "json": "jsonl",
            "jsonl": "jsonl",
            "parquet": "parquet",
            "pq": "parquet",
        }

        format_name = extension_map.get(ext)
        if format_name:
            return self.get(format_name)
        return None

    @property
    def available_formats(self) -> list[str]:
        """Return list of registered format names."""
        return sorted(self._parsers.keys())


def get_parser(format_name: str) -> Optional[BaseParser]:
    """Convenience function to get a parser by format name.

    Args:
        format_name: The format name (e.g., 'csv', 'jsonl', 'parquet').

    Returns:
        The parser for the format, or None if not registered.
    """
    return ParserRegistry.get_instance().get(format_name)
