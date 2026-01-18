"""Generic S3 file processor moved to etl_core."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional
from botocore.exceptions import ClientError

from packages.etl_core.config import S3Config
from packages.etl_core.s3 import S3Client

logger = logging.getLogger(__name__)


class S3FileProcessor(S3Client):
    """Simplified S3 file processor for copying files between buckets.

    This class provides functionality for copying files between S3 buckets with
    retry logic, progress tracking, and metadata upload capabilities.

    It is intentionally generic: job-specific conventions (mapping key names,
    agency/tenant folder logic, metadata filename/subfolder conventions) must be
    provided by caller code (for example from `packages/pipeline_processing`).
    """

    def __init__(
            self,
            config: S3Config,
            s3_client: Optional[Any] = None,
            *,
            mapping_keys: Optional[Dict[str, str]] = None,
            agency_prefix_fn: Optional[Callable[[], str]] = None,
            destination_key_fn: Optional[Callable[[str, str], str]] = None,
    ) -> None:
        """Initialize the processor.

        Args:
            config: S3Config instance.
            s3_client: Optional S3 client (injected for testing).
            mapping_keys: Optional mapping for expected keys in file mappings. Example:
                {"filename": "filename", "output_filename": "output_filename"}
                This allows job code to adapt different mapping shapes.
            agency_prefix_fn: Optional callable that returns a prefix (e.g. agency folder)
                to prepend to destination keys. If not provided, no prefix is used.
            destination_key_fn: Optional callable that builds the final destination key
                given (agency_prefix, output_filename). If not provided, a default
                of "{agency_prefix}{config.destination_prefix.rstrip('/')}/{output_filename}"
                is used.
        """
        super().__init__(config, s3_client)
        self._progress_callback: Optional[Callable[[int, int, str], None]] = None
        # default mapping keys (keeps current behaviour unless overridden)
        self.mapping_keys = mapping_keys or {"filename": "filename", "output_filename": "output_filename"}
        # hook to get an agency/tenant prefix; caller provides it if needed
        self.agency_prefix_fn = agency_prefix_fn
        # hook to produce destination key; caller can fully control layout
        self.destination_key_fn = destination_key_fn

    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        self._progress_callback = callback

    def process_files(self, file_mappings: List[Dict[str, Any]], concurrent: bool = True) -> List[Dict[str, Any]]:
        """Process a list of file mapping dictionaries.

        Args:
            file_mappings: List of mappings describing source and destination names.
            concurrent: If True, process using a thread pool. If False, process sequentially.

        Returns:
            List of result dicts for each mapping.
        """
        results: List[Dict[str, Any]] = []
        completed = 0

        if concurrent:
            with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                future_to_mapping = {
                    executor.submit(self._copy_single_file, mapping): mapping
                    for mapping in file_mappings
                }

                for future in as_completed(future_to_mapping):
                    result = future.result()
                    results.append(result)
                    completed += 1

                    if self._progress_callback:
                        mapping = future_to_mapping[future]
                        filename_key = self.mapping_keys.get("filename", "filename")
                        self._progress_callback(completed, len(file_mappings), mapping.get(filename_key))
        else:
            # sequential processing (easier to debug and deterministic for some jobs)
            for mapping in file_mappings:
                result = self._copy_single_file(mapping)
                results.append(result)
                completed += 1
                if self._progress_callback:
                    filename_key = self.mapping_keys.get("filename", "filename")
                    self._progress_callback(completed, len(file_mappings), mapping.get(filename_key))

        return results

    def _copy_single_file(self, mapping: Dict[str, Any]) -> Dict[str, Any]:
        """Copy a single file according to the provided mapping.

        The mapping shape is configurable via `mapping_keys` to keep this class
        generic. The final destination key is produced either by `destination_key_fn`
        or by the default layout using `config.destination_prefix` and an optional
        agency prefix from `agency_prefix_fn`.
        """
        filename_key = self.mapping_keys.get("filename", "filename")
        output_key_name = self.mapping_keys.get("output_filename", "output_filename")

        source_key = mapping.get(filename_key, "")
        output_filename = mapping.get(output_key_name, "")

        if not source_key or not output_filename:
            return {
                "source_key": source_key,
                "destination_key": None,
                "status": "error",
                "message": "Missing filename or output_filename in mapping"
            }

        # If caller did not provide an agency_prefix_fn, fall back to the configured
        # agency folder from the S3 client base implementation. This keeps behavior
        # backward-compatible with callers that expect `config.agency_s3_slug` to
        # be used when building destination keys.
        agency_prefix = self.agency_prefix_fn() if self.agency_prefix_fn else self._get_agency_folder()

        if self.destination_key_fn:
            destination_key = self.destination_key_fn(agency_prefix, output_filename)
        else:
            destination_key = f"{agency_prefix}{self.config.destination_prefix.rstrip('/')}/{output_filename}"

        for attempt in range(1, self.config.retry_attempts + 1):
            try:
                response = self.s3_client.head_object(
                    Bucket=self.config.source_bucket,
                    Key=source_key
                )
                file_size = response["ContentLength"]

                copy_source = {"Bucket": self.config.source_bucket, "Key": source_key}
                self.s3_client.copy_object(
                    CopySource=copy_source,
                    Bucket=self.config.destination_bucket,
                    Key=destination_key
                )

                return {
                    "source_key": source_key,
                    "destination_key": destination_key,
                    "status": "success",
                    "message": f"Successfully copied {source_key} to {destination_key}",
                    "file_size": file_size
                }

            except Exception as e:
                # Normalize AWS ClientError-like exceptions which carry a `.response` dict
                aws_response = getattr(e, "response", None)
                # Some test harnesses construct ClientError-like exceptions where
                # the response is available as one of the positional args instead of
                # an attribute. Search args for a dict payload; also handle nested
                # tuple-wrapped payloads introduced by various mocking layers.
                if aws_response is None and getattr(e, 'args', None):
                    try:
                        def find_dict(obj):
                            if isinstance(obj, dict):
                                return obj
                            if isinstance(obj, (list, tuple)):
                                for item in obj:
                                    found = find_dict(item)
                                    if found is not None:
                                        return found
                            return None

                        aws_response = find_dict(e.args)
                    except Exception:
                        aws_response = None
                if isinstance(aws_response, dict):
                    # Extract code/message when available
                    try:
                        error_code = aws_response["Error"]["Code"]
                        error_message = aws_response["Error"].get("Message", "")
                    except Exception:
                        error_code = None
                        error_message = str(aws_response)

                    # Treat not-found cases consistently
                    if error_code in ["NoSuchKey", "404"]:
                        return {
                            "source_key": source_key,
                            "destination_key": destination_key,
                            "status": "not_found",
                            "message": f"File not found: {source_key}"
                        }

                    # For other AWS errors, retry when attempts remain
                    if attempt < self.config.retry_attempts:
                        time.sleep(attempt)
                        continue

                    return {
                        "source_key": source_key,
                        "destination_key": destination_key,
                        "status": "error",
                        "message": f"AWS error ({error_code}): {error_message}"
                    }

                # Non-AWS exceptions: retry a few times then surface unexpected error
                if attempt < self.config.retry_attempts:
                    time.sleep(attempt)
                    continue
                return {
                    "source_key": source_key,
                    "destination_key": destination_key,
                    "status": "error",
                    "message": f"Unexpected error: {str(e)}"
                }

    def upload_metadata_csv(
            self,
            query_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Upload metadata CSV to S3.

        This method is intentionally generic: callers provide filename_prefix,
        subfolder and record_count_key as they see fit for their job.
        """
        if not query_results:
            return {"status": "error", "message": "No query results to upload"}

        fieldnames = list(query_results[0].keys())
        # Use canonical metadata naming convention for attachment manifests
        return self.upload_data_as_csv(
            data=query_results,
            fieldnames=fieldnames,
            filename_prefix="metadata",
            subfolder="attachment_manifest",
            record_count_key="records_count",
        )
