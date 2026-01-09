"""S3 Data Quality Job entrypoint.

This job orchestrates the processing of a single S3 file for data quality checks.
It is invoked by the SNS listener (for real-time events) or manually via CLI.
"""
import argparse
import json
import logging
import os
from typing import List
from urllib.parse import unquote_plus

from etl_core.database.client import DatabaseClient
from etl_core.config.config import S3Config
from etl_core.s3.client import S3Client

from file_processing.models.events import S3Event
from file_processing.processors.s3_data_quality_processor import (
    S3DataQualityProcessor,
    S3DataQualityProcessorConfig,
)
from file_processing.repositories.monitoring_repository import MonitoringRepository

logger = logging.getLogger(__name__)


def _extract_s3_events(payload: dict) -> List[S3Event]:
    """Extract S3Events from various trigger payloads (Direct, S3, SNS)."""
    events = []

    # helper to process an S3-style event dict (with Records)
    def process_s3_event_payload(payload_data):
        if not isinstance(payload_data, dict):
            return []
        recs = payload_data.get("Records", [])
        extracted = []
        for rec in recs:
            if "s3" in rec:
                s3_info = rec["s3"]
                bucket = s3_info.get("bucket", {}).get("name")
                key = s3_info.get("object", {}).get("key")
                if bucket and key:
                    # S3 keys in events are URL-encoded
                    key = unquote_plus(key)
                    extracted.append(S3Event(bucket=bucket, key=key))
        return extracted

    # Case 1: Direct invocation payload {"bucket": "...", "key": "..."}
    if "bucket" in payload and "key" in payload:
        return [S3Event(bucket=payload["bucket"], key=payload["key"])]

    # Case 2: Standard S3 Event or wrapper
    records = payload.get("Records", [])
    if records:
        # Check if first record is SNS
        first_rec = records[0]

        # SNS Wrapping
        if "Sns" in first_rec and "Message" in first_rec["Sns"]:
            for rec in records:
                if "Sns" in rec:
                    try:
                        message = rec["Sns"]["Message"]
                        inner_payload = json.loads(message)
                        events.extend(process_s3_event_payload(inner_payload))
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning("Failed to parse SNS message: %s", e)

        # Standard S3 Event
        elif "s3" in first_rec:
            events.extend(process_s3_event_payload(payload))

    return events


def entrypoint(argv: List[str]) -> int:
    """Entrypoint for the s3_data_quality_job.

    Args:
        argv: Command line arguments (excluding the script name).

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(description="Process S3 file for data quality")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--event-json",
        help="JSON string of the S3 event (AWS S3 notification format)",
    )
    group.add_argument(
        "--event-file",
        help="Path to a file containing the JSON event payload",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without persisting changes to the database",
    )

    # Configure basic logging to ensuring INFO logs appear on stdout
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,  # Ensure we override any existing config if this entrypoint is called
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        # argparse calls sys.exit(), catch it to return int
        return 2

    try:
        # Parse the AWS S3 event JSON
        event_json_str = args.event_json
        if args.event_file:
            try:
                with open(args.event_file, "r", encoding="utf-8") as f:
                    event_json_str = f.read()
            except IOError as e:
                logger.error("Failed to read event file '%s': %s", args.event_file, e)
                return 1

        try:
            event_payload = json.loads(event_json_str)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON provided in event payload: %s", e)
            return 1

        # Use extraction helper
        s3_events = _extract_s3_events(event_payload)

        if not s3_events:
            # Fallback: check if we just parsed a list of records but extraction logic missed it
            # The previous code handled logic inline; users might expect direct Records parsing
            logger.error("No S3 events found in payload")
            return 1

        # Initialize dependencies
        try:
            db_client = DatabaseClient()  # Config from env vars
            # S3Config requires bucket args even if not used by the processor which uses event.bucket
            s3_config = S3Config(
                source_bucket=os.getenv("S3_SOURCE_BUCKET", "ignored"),
                destination_bucket=os.getenv("S3_DESTINATION_BUCKET", "ignored"),
                agency_s3_slug=os.getenv("AGENCY_S3_SLUG", "ignored"),
            )
            s3_client = S3Client(config=s3_config)
            repo = MonitoringRepository(db_client)
        except Exception as e:
            logger.exception("Failed to initialize job dependencies: %s", e)
            return 1

        # Configure processor
        processor_config = S3DataQualityProcessorConfig(
            dry_run=args.dry_run,
            # Defaults for other config options
        )

        processor = S3DataQualityProcessor(
            repository=repo,
            s3_client=s3_client,
            config=processor_config,
        )

        failure_count = 0
        for i, event in enumerate(s3_events):
            logger.info("Processing s3://%s/%s", event.bucket, event.key)

            try:
                result = processor.process_s3_event(event)
                logger.info(
                    "Success: %s (Quality Score: %s)",
                    event.key,
                    result.score if result else "N/A",
                )
            except Exception as e:
                logger.exception("Failed to process object %s", event.key)
                failure_count += 1

        if failure_count > 0:
            logger.error("Job completed with %d failure(s)", failure_count)
            return 1

        logger.info("Job completed successfully")
        return 0

    except Exception as e:
        logger.exception("Unexpected error in main job execution: %s", e)
        return 1


JOB = (entrypoint, "Process S3 file for data quality")
