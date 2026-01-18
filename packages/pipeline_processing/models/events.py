"""Event models for S3 notifications and pipeline input."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class S3Event:
    """Represents an S3 object-created notification.

    This is the primary input to the data quality pipeline.
    The key is parsed to extract agency_slug, file_name, run_date, and run_hour.
    """

    bucket: str
    key: str
    last_modified: Optional[datetime] = None
    size: Optional[int] = None

    # Optional overrides (set by callers or the CLI) to control which run this
    # event should map to when the key does not encode run date/hour.
    override_run_date: Optional[date] = None
    override_run_hour: Optional[int] = None

    def parse_key(self) -> "ParsedS3Key":
        """Parse the S3 key to extract routing information.

        Expected key format (preferred):
            agency/<agency_slug>/files/<file_name>/<YYYY-MM-DD>/<HH>/data.<ext>

        The parser is intentionally permissive: if the preferred format is not
        matched we attempt heuristics to extract an `agency_slug` and
        `file_name` from other common layouts (for example the upstream stub
        keys like `from_client/<agency_slug>/.../<file_name>`). When date/hour
        are not present we use an explicit override (if provided) or fall back
        to the `last_modified` timestamp or current UTC date/hour.

        Returns:
            ParsedS3Key with extracted fields.

        Raises:
            ValueError: If the key format is not recognized and heuristics fail.
        """
        parts = self.key.strip("/").split("/")

        # First, attempt to parse the canonical (strict) format.
        try:
            if len(parts) < 6:
                raise ValueError("not enough parts for strict format")

            if parts[0] != "agency" or parts[2] != "files":
                raise ValueError("not canonical prefix")

            agency_slug = parts[1]
            file_name = parts[3]
            run_date_str = parts[4]
            run_hour_str = parts[5]

            try:
                run_date = datetime.strptime(run_date_str, "%Y-%m-%d").date()
            except ValueError as exc:
                raise ValueError(f"Invalid date in S3 key: {run_date_str}") from exc

            try:
                run_hour = int(run_hour_str)
                if not 0 <= run_hour <= 23:
                    raise ValueError(f"Hour must be 0-23, got {run_hour}")
            except ValueError as exc:
                raise ValueError(f"Invalid hour in S3 key: {run_hour_str}") from exc

            # Detect file format from extension
            filename = parts[-1] if len(parts) > 6 else "data.csv"

            file_format = "csv"
            if filename.endswith(".json") or filename.endswith(".jsonl"):
                file_format = "jsonl"
            elif filename.endswith(".parquet"):
                file_format = "parquet"

            return ParsedS3Key(
                agency_slug=agency_slug,
                file_name=file_name,
                run_date=run_date,
                run_hour=run_hour,
                file_format=file_format,
            )
        except ValueError as exc:
            # If the error was due to invalid date/hour in canonical path, re-raise it
            if "Invalid date" in str(exc) or "Invalid hour" in str(exc):
                raise
            # Fall back to permissive heuristics for known legacy/layout cases only.
            if len(parts) >= 2 and parts[0] in ("from_client", "from-client"):
                agency_slug = parts[1]
                file_name = parts[-1]
            elif len(parts) >= 2 and parts[0] == "uploads":
                # uploads/<agency>/<file>
                agency_slug = parts[1]
                file_name = parts[-1]
            elif len(parts) == 1:
                # Single filename (local/dev convenience)
                agency_slug = ""
                file_name = parts[0]
            else:
                # Unknown layout - be strict and raise a helpful error
                raise ValueError(
                    f"S3 key '{self.key}' does not match expected format: agency/<agency_slug>/files/<file_name>/<date>/<hour>/..."
                )

            # Determine run_date and run_hour from overrides, last_modified, or now (UTC)
            if self.override_run_date is not None:
                run_date = self.override_run_date
            elif self.last_modified is not None:
                run_date = self.last_modified.date()
            else:
                run_date = datetime.utcnow().date()

            if self.override_run_hour is not None:
                run_hour = int(self.override_run_hour)
            elif self.last_modified is not None:
                run_hour = int(self.last_modified.hour)
            else:
                run_hour = int(datetime.utcnow().hour)

            # Detect file format
            filename = parts[-1]
            file_format = "csv"
            if filename.endswith(".json") or filename.endswith(".jsonl"):
                file_format = "jsonl"
            elif filename.endswith(".parquet"):
                file_format = "parquet"

            return ParsedS3Key(
                agency_slug=agency_slug,
                file_name=file_name,
                run_date=run_date,
                run_hour=run_hour,
                file_format=file_format,
            )


@dataclass
class ParsedS3Key:
    """Parsed components from an S3 key."""

    agency_slug: str
    file_name: str
    run_date: "datetime.date"
    run_hour: int
    file_format: str = "csv"

    @property
    def run_date_str(self) -> str:
        """Return run_date as string in YYYY-MM-DD format."""
        return self.run_date.strftime("%Y-%m-%d")


# Re-import date for type annotation
from datetime import date as date_type  # noqa: E402
ParsedS3Key.__annotations__["run_date"] = date_type
