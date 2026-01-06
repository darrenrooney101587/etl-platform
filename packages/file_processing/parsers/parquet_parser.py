"""Parquet file parser implementation."""
from __future__ import annotations

import logging
from typing import Any, Dict, IO, List

from file_processing.parsers.base import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class ParquetParser(BaseParser):
    """Parser for Parquet files.

    Requires pyarrow to be installed.
    """

    @property
    def format_name(self) -> str:
        """Return the format name."""
        return "parquet"

    def parse(self, file_obj: IO[bytes]) -> ParseResult:
        """Parse a Parquet file.

        Args:
            file_obj: A file-like object opened in binary mode.

        Returns:
            ParseResult with parsed data or error information.
        """
        try:
            import pyarrow.parquet as pq
        except ImportError:
            return ParseResult(
                success=False,
                error_message="pyarrow is required to parse Parquet files. Install with: pip install pyarrow",
            )

        try:
            # Read parquet from bytes
            import io

            # Read all bytes and create a BytesIO for pyarrow
            content = file_obj.read()
            buffer = io.BytesIO(content)

            table = pq.read_table(buffer)
            df_dict = table.to_pydict()

            # Convert columnar format to row format
            columns = list(df_dict.keys())
            if not columns:
                return ParseResult(
                    success=True,
                    rows=[],
                    columns=[],
                    row_count=0,
                )

            num_rows = len(df_dict[columns[0]]) if columns else 0
            rows: List[Dict[str, Any]] = []

            for i in range(num_rows):
                row = {col: df_dict[col][i] for col in columns}
                # Convert numpy/pyarrow types to Python native types
                cleaned_row = self._convert_row_types(row)
                rows.append(cleaned_row)

            return ParseResult(
                success=True,
                rows=rows,
                columns=columns,
                row_count=len(rows),
            )

        except Exception as exc:
            logger.exception("Error parsing Parquet file")
            return ParseResult(
                success=False,
                error_message=f"Parquet parsing error: {exc}",
            )

    def _convert_row_types(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert numpy/pyarrow types to Python native types.

        Args:
            row: A dictionary with potentially non-native types.

        Returns:
            Dictionary with Python native types.
        """
        result: Dict[str, Any] = {}
        for key, value in row.items():
            if value is None:
                result[key] = None
            elif hasattr(value, "item"):  # numpy scalar
                result[key] = value.item()
            elif hasattr(value, "as_py"):  # pyarrow scalar
                result[key] = value.as_py()
            else:
                result[key] = value
        return result
