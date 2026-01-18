"""Base parser interface and common types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, IO, List, Optional


@dataclass
class ParseResult:
    """Result from parsing a file.

    Attributes:
        success: Whether parsing succeeded.
        rows: List of parsed rows as dictionaries.
        columns: List of column names in order.
        row_count: Total number of rows parsed.
        error_message: Error message if parsing failed.
        warnings: List of non-fatal parsing warnings.
    """

    success: bool
    rows: List[Dict[str, Any]] = field(default_factory=list)
    columns: List[str] = field(default_factory=list)
    row_count: int = 0
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


class BaseParser(ABC):
    """Abstract base class for file parsers.

    All parsers must implement the parse method which accepts a file-like
    object and returns a ParseResult.
    """

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Return the format name this parser handles (e.g., 'csv', 'jsonl')."""
        ...

    @abstractmethod
    def parse(self, file_obj: IO[bytes]) -> ParseResult:
        """Parse the file and return a ParseResult.

        Args:
            file_obj: A file-like object opened in binary mode.

        Returns:
            ParseResult with parsed data or error information.
        """
        ...

    def parse_bytes(self, data: bytes) -> ParseResult:
        """Parse from raw bytes.

        Args:
            data: Raw bytes of the file content.

        Returns:
            ParseResult with parsed data or error information.
        """
        import io
        return self.parse(io.BytesIO(data))
