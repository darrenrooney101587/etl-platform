"""Job-specific adapters for the generic S3FileProcessor.

This module lives under `packages/data_pipeline` and provides small wrappers
that apply business conventions (agency prefix, destination key layout,
mapping keys, metadata filenames) while keeping `etl_core` generic.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from etl_core.config import S3Config
from etl_core.processors.s3_file_processor import S3FileProcessor


def make_agency_prefix_fn(agency_id: str) -> Callable[[], str]:
    """Return a callable that yields the agency prefix used for destination keys.

    The returned callable includes a trailing slash so callers do not need to
    add separators.

    Args:
        agency_id: Agency / tenant identifier.

    Returns:
        Callable that returns a prefix string when called.
    """

    def _fn() -> str:
        return f"{agency_id.rstrip('/')}/" if agency_id else ""

    return _fn


def make_destination_key_fn(destination_prefix: str) -> Callable[[str, str], str]:
    """Create a destination key builder using the configured destination_prefix.

    Args:
        destination_prefix: Prefix configured in the S3Config (may include folder path).

    Returns:
        Callable that accepts (agency_prefix, output_filename) and returns a S3 key.
    """

    def _fn(agency_prefix: str, output_filename: str) -> str:
        base = destination_prefix.rstrip('/')
        if agency_prefix:
            return f"{agency_prefix}{base}/{output_filename}"
        return f"{base}/{output_filename}"

    return _fn


def get_configured_processor(
        config: S3Config,
        *,
        agency_id: Optional[str] = None,
        mapping_keys: Optional[Dict[str, str]] = None,
) -> S3FileProcessor:
    """Return an S3FileProcessor configured for the data_pipeline job.

    This function wires job-specific conventions into the generic processor.

    Args:
        config: S3Config instance.
        agency_id: Optional agency identifier to include as a folder prefix.
        mapping_keys: Optional mapping keys for input mappings.

    Returns:
        Configured S3FileProcessor instance ready for use by job code.
    """

    agency_prefix_fn = make_agency_prefix_fn(agency_id) if agency_id else None
    destination_key_fn = make_destination_key_fn(config.destination_prefix)
    mapping_keys = mapping_keys or {"filename": "filename", "output_filename": "output_filename"}

    return S3FileProcessor(
        config=config,
        mapping_keys=mapping_keys,
        agency_prefix_fn=agency_prefix_fn,
        destination_key_fn=destination_key_fn,
    )


def upload_attachment_manifest(processor: S3FileProcessor, query_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Upload the job-specific attachment manifest CSV using standard conventions.

    This helper keeps the naming/layout convention in the job module so the
    core processor remains generic.

    Args:
        processor: Configured S3FileProcessor instance.
        query_results: List of dicts representing the metadata rows.

    Returns:
        Result dict returned by S3FileProcessor.upload_metadata_csv.
    """

    return processor.upload_metadata_csv(
        query_results,
        filename_prefix="metadata",
        subfolder="attachment_manifest",
        record_count_key="records_count",
    )
