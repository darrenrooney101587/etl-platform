"""S3 Data Quality Job with PDF Report Generation and Email Notification.

This job extends the standard s3_data_quality_job by adding:
1. PDF report generation using headless browser (Playwright)
2. Email notification with PDF attachment via SendGrid

The job runs the full data quality pipeline and, upon successful completion,
generates a PDF report from the frontend and emails it to configured recipients.
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
from file_processing.processors.pdf_generator import PDFGenerator, PDFGeneratorConfig
from file_processing.processors.email_sender import EmailSender, EmailSenderConfig
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
    """Entrypoint for s3_data_quality_with_pdf_email job.

    This job runs data quality checks, then generates a PDF report and emails it.

    Args:
        argv: Command line arguments (excluding the script name).

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Process S3 file for data quality, generate PDF report, and send email"
    )

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

    parser.add_argument(
        "--trace-id",
        help="Optional trace ID for logging context",
        default=None,
    )

    parser.add_argument(
        "--skip-pdf",
        action="store_true",
        help="Skip PDF generation and email sending",
    )

    parser.add_argument(
        "--email-recipients",
        help="Comma-separated list of email recipients (overrides default)",
        default=None,
    )

    is_main_script = __name__ == "__main__" or "s3_data_quality_with_pdf_email" in str(argv)

    if is_main_script and not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2

    trace_prefix = f"[{args.trace_id}] " if args.trace_id else ""

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

        s3_events = _extract_s3_events(event_payload)

        if not s3_events:
            logger.error("No S3 events found in payload")
            return 1

        try:
            if not os.getenv("DJANGO_SETTINGS_MODULE"):
                os.environ["DJANGO_SETTINGS_MODULE"] = "file_processing.settings"
            import django  # type: ignore

            django.setup()

            db_client = DatabaseClient()
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

        processor_config = S3DataQualityProcessorConfig(dry_run=args.dry_run)

        processor = S3DataQualityProcessor(
            repository=repo,
            s3_client=s3_client,
            config=processor_config,
        )

        # Process data quality for all events
        failure_count = 0
        success_count = 0
        for event in s3_events:
            logger.info("%sProcessing s3://%s/%s", trace_prefix, event.bucket, event.key)

            try:
                result = processor.process_s3_event(event)

                passed = getattr(result, "passed", True)
                if not passed:
                    logger.error(
                        "%sProcessing completed but reported failure for %s (score=%s)",
                        trace_prefix,
                        event.key,
                        getattr(result, "score", "N/A"),
                    )
                    failure_count += 1
                else:
                    logger.info(
                        "%sSuccess: %s (Quality Score: %s)",
                        trace_prefix,
                        event.key,
                        getattr(result, "score", "N/A"),
                    )
                    success_count += 1

            except Exception as e:
                logger.exception("%sFailed to process object %s", trace_prefix, event.key)
                failure_count += 1

        # If data quality processing succeeded and not skipping PDF, generate PDF and send email
        if success_count > 0 and not args.skip_pdf:
            logger.info("%sData quality processing complete. Generating PDF report...", trace_prefix)

            try:
                # Generate PDF using headless browser
                pdf_config = PDFGeneratorConfig()
                pdf_generator = PDFGenerator(config=pdf_config)

                # Add query parameters to identify the report
                query_params = {
                    "run_id": s3_events[0].key if s3_events else "unknown",
                    "timestamp": str(int(__import__("time").time())),
                }

                pdf_path = pdf_generator.generate_pdf(query_params=query_params)
                logger.info("%sPDF generated: %s", trace_prefix, pdf_path)

                # Send email with PDF attachment
                email_config = EmailSenderConfig()
                email_sender = EmailSender(config=email_config)

                # Parse recipients if provided
                recipients = None
                if args.email_recipients:
                    recipients = [r.strip() for r in args.email_recipients.split(",")]

                email_body = (
                    f"Data Quality Processing Complete\n\n"
                    f"Successfully processed {success_count} file(s).\n"
                    f"Failed to process {failure_count} file(s).\n\n"
                    f"Please find the detailed data quality report attached.\n\n"
                    f"This is an automated message from the ETL Platform Data Quality system."
                )

                email_sender.send_email(
                    to_addresses=recipients,
                    subject=f"Data Quality Report - {success_count} file(s) processed",
                    body_text=email_body,
                    attachment_paths=[pdf_path],
                )

                logger.info("%sEmail sent successfully", trace_prefix)

            except Exception as e:
                logger.exception("%sFailed to generate PDF or send email: %s", trace_prefix, e)
                # Don't fail the entire job if PDF/email fails
                logger.warning("%sContinuing despite PDF/email failure", trace_prefix)

        if failure_count > 0:
            logger.error("%sJob completed with %d failure(s)", trace_prefix, failure_count)
            return 1

        logger.info("%sJob completed successfully", trace_prefix)
        return 0

    except Exception as e:
        logger.exception("%sUnexpected error in main job execution: %s", trace_prefix, e)
        return 1


JOB = (entrypoint, "Process S3 file for data quality, generate PDF, and send email")
