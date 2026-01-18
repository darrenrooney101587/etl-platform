"""JSONL (JSON Lines) file parser implementation."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, IO, List, Set

from pipeline_processing.parsers.base import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class JsonlParser(BaseParser):
    """Parser for JSONL (JSON Lines) files.

    Each line is expected to be a valid JSON object.
    """

    def __init__(self, encoding: str = "utf-8") -> None:
        """Initialize the JSONL parser.

        Args:
            encoding: Character encoding for the file.
        """
        self._encoding = encoding

    @property
    def format_name(self) -> str:
        """Return the format name."""
        return "jsonl"

    def parse(self, file_obj: IO[bytes]) -> ParseResult:
        """Parse a JSONL file.

        Args:
            file_obj: A file-like object opened in binary mode.

        Returns:
            ParseResult with parsed data or error information.
        """
        try:
            content = file_obj.read().decode(self._encoding)
            lines = content.strip().split("\n")

            rows: List[Dict[str, Any]] = []
            warnings: List[str] = []
            all_columns: Set[str] = set()

            for line_num, line in enumerate(lines, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    obj = json.loads(line)
                    if not isinstance(obj, dict):
                        warnings.append(
                            f"Line {line_num}: Expected JSON object, got {type(obj).__name__}"
                        )
                        continue
                    rows.append(obj)
                    all_columns.update(obj.keys())
                except json.JSONDecodeError as exc:
                    warnings.append(f"Line {line_num}: JSON parse error - {exc}")

            # If too many lines failed, consider it a parse failure
            if len(warnings) > len(rows):
                return ParseResult(
                    success=False,
                    error_message=f"Too many JSON parse errors ({len(warnings)} errors, {len(rows)} valid rows)",
                    warnings=warnings[:10],  # Limit warning output
                )

            # Sort columns for consistent ordering
            columns = sorted(all_columns)

            return ParseResult(
                success=True,
                rows=rows,
                columns=columns,
                row_count=len(rows),
                warnings=warnings[:10] if warnings else [],
            )

        except UnicodeDecodeError as exc:
            return ParseResult(
                success=False,
                error_message=f"Failed to decode JSONL as {self._encoding}: {exc}",
            )
        except Exception as exc:
            logger.exception("Unexpected error parsing JSONL")
            return ParseResult(
                success=False,
                error_message=f"Unexpected error parsing JSONL: {exc}",
            )
