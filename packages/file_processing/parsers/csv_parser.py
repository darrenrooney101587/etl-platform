"""CSV file parser implementation."""
from __future__ import annotations

import csv
import io
import logging
from typing import Any, Dict, IO, List

from file_processing.parsers.base import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class CsvParser(BaseParser):
    """Parser for CSV files (UTF-8 with header row)."""

    def __init__(self, encoding: str = "utf-8", delimiter: str = ",") -> None:
        """Initialize the CSV parser.

        Args:
            encoding: Character encoding for the CSV file.
            delimiter: Field delimiter character.
        """
        self._encoding = encoding
        self._delimiter = delimiter

    @property
    def format_name(self) -> str:
        """Return the format name."""
        return "csv"

    def parse(self, file_obj: IO[bytes]) -> ParseResult:
        """Parse a CSV file.

        Args:
            file_obj: A file-like object opened in binary mode.

        Returns:
            ParseResult with parsed data or error information.
        """
        try:
            # Decode bytes to text
            text_content = file_obj.read().decode(self._encoding)
            text_io = io.StringIO(text_content)

            # Use csv.DictReader for header-based parsing
            reader = csv.DictReader(text_io, delimiter=self._delimiter)

            rows: List[Dict[str, Any]] = []
            warnings: List[str] = []

            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is 1)
                # Convert empty strings to None for consistency
                cleaned_row = {
                    k: (v if v != "" else None)
                    for k, v in row.items()
                    if k is not None  # Skip rows with more fields than headers
                }
                rows.append(cleaned_row)

            columns = reader.fieldnames or []

            return ParseResult(
                success=True,
                rows=rows,
                columns=list(columns),
                row_count=len(rows),
                warnings=warnings,
            )

        except UnicodeDecodeError as exc:
            return ParseResult(
                success=False,
                error_message=f"Failed to decode CSV as {self._encoding}: {exc}",
            )
        except csv.Error as exc:
            return ParseResult(
                success=False,
                error_message=f"CSV parsing error: {exc}",
            )
        except Exception as exc:
            logger.exception("Unexpected error parsing CSV")
            return ParseResult(
                success=False,
                error_message=f"Unexpected error parsing CSV: {exc}",
            )
