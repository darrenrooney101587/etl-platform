"""Job entrypoint for the S3 data quality pipeline.

This job processes S3 object-created events and computes data quality metrics.
It can operate in two modes:
1. Single event mode: Process a single S3 event from CLI arguments

Contract:
- Exports `JOB = (entrypoint, description)` for job discovery.
- `entrypoint(argv: List[str]) -> int` accepts CLI arguments and returns exit code.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import ast

from etl_core.database.client import DatabaseClient
from etl_core.s3.client import S3Client, build_s3_client
from etl_core.config.config import S3Config
from file_processing.models.events import S3Event
from file_processing.processors.s3_data_quality_processor import (
    S3DataQualityProcessor,
    S3DataQualityProcessorConfig,
)
from file_processing.repositories.monitoring_repository import MonitoringRepository

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool = False) -> None:
    """Configure structured logging.

    Args:
        verbose: If True, set DEBUG level; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _build_s3_config() -> S3Config:
    """Build S3Config from environment variables.

    Returns:
        S3Config instance.
    """
    return S3Config(
        source_bucket=os.getenv("S3_SOURCE_BUCKET", ""),
        destination_bucket=os.getenv("S3_DESTINATION_BUCKET", ""),
        agency_s3_slug=os.getenv("AGENCY_S3_SLUG", ""),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_region=os.getenv("AWS_REGION", "us-gov-west-1"),
    )


def _parse_s3_event(event_json: str) -> S3Event:
    """Parse an S3 event from JSON string.

    Args:
        event_json: JSON string with bucket, key, and optional metadata.

    Returns:
        S3Event instance.

    Raises:
        ValueError: If required fields are missing.
    """
    data = json.loads(event_json)

    if "bucket" not in data or "key" not in data:
        raise ValueError("S3 event must contain 'bucket' and 'key' fields")

    last_modified = None
    if "last_modified" in data:
        try:
            dt = datetime.fromisoformat(data["last_modified"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            last_modified = dt
        except ValueError:
            logger.warning("Invalid last_modified date format: %s", data["last_modified"])

    return S3Event(
        bucket=data["bucket"],
        key=data["key"],
        last_modified=last_modified,
        size=data.get("size"),
    )


def _extract_s3_events(payload: Dict[str, Any]) -> List[S3Event]:
    """Extract one or more S3Event objects from an AWS-style payload.

    Supports:
    - Direct: {"bucket": "...", "key": "..."}
    - S3 event: {"Records": [{"s3": {"bucket": {"name": ...}, "object": {"key": ...}}}]}
    - SNS: {"Records": [{"Sns": {"Message": "{...}"}}]}
    - SQS: {"Records": [{"body": "{...}"}]}

    Args:
        payload: Decoded JSON payload.

    Returns:
        List of S3Event objects.

    Raises:
        ValueError: If no S3 events can be extracted.
    """
    # Direct format
    if "bucket" in payload and "key" in payload:
        return [_parse_s3_event(json.dumps(payload))]

    # AWS Records wrapper
    records = payload.get("Records")
    if not isinstance(records, list):
        raise ValueError("Unsupported event payload (missing Records or bucket/key)")

    events: List[S3Event] = []
    for rec in records:
        if isinstance(rec, dict) and "Sns" in rec and isinstance(rec["Sns"], dict) and "Message" in rec["Sns"]:
            inner = json.loads(rec["Sns"]["Message"])
            events.extend(_extract_s3_events(inner))
            continue

        if isinstance(rec, dict) and "body" in rec:
            inner = json.loads(rec["body"])
            events.extend(_extract_s3_events(inner))
            continue

        s3 = rec.get("s3") if isinstance(rec, dict) else None
        if isinstance(s3, dict):
            bucket_name = (s3.get("bucket") or {}).get("name")
            key = (s3.get("object") or {}).get("key")
            if bucket_name and key:
                events.append(S3Event(bucket=bucket_name, key=key))

    if not events:
        raise ValueError("No S3 records found in Records payload")

    return events


def _process_single_event(
    processor: S3DataQualityProcessor,
    event: S3Event,
) -> Dict[str, Any]:
    """Process a single S3 event.

    Args:
        processor: The S3DataQualityProcessor instance.
        event: S3Event to process.

    Returns:
        Dictionary with processing result.
    """
    try:
        result = processor.process_s3_event(event)
        return {
            "status": "success" if result.passed else "warning",
            "bucket": event.bucket,
            "key": event.key,
            "score": result.score,
            "passed": result.passed,
            "deductions": result.deductions.to_dict(),
        }
    except Exception as exc:
        logger.exception("Failed to process event: %s/%s", event.bucket, event.key)
        return {
            "status": "error",
            "bucket": event.bucket,
            "key": event.key,
            "error": str(exc),
        }


def _print_result(result: Dict[str, Any]) -> None:
    """Print processing result.

    Args:
        result: Result dictionary to print.
    """
    status = result.get("status", "unknown")
    bucket = result.get("bucket", "")
    key = result.get("key", "")

    if status == "error":
        print(f"ERROR: {bucket}/{key} - {result.get('error')}")
    else:
        score = result.get("score", 0)
        passed = result.get("passed", False)
        passed_str = "PASSED" if passed else "FAILED"
        print(f"{passed_str}: {bucket}/{key} - Score: {score}")


def _tolerant_parse_event_json(raw: str) -> Any:
    """Tolerantly parse an event payload string.

    Attempts, in order:
    1. json.loads
    2. ast.literal_eval (Python dict/list literal)
    3. Heuristic fixer that quotes bare keys and unquoted string values
       (used only as a last resort for IDEs that strip quotes)

    Returns the parsed object (dict/list) or raises ValueError.
    """
    # 1) Strict JSON
    try:
        return json.loads(raw)
    except Exception:
        pass

    # 2) Python literal
    try:
        return ast.literal_eval(raw)
    except Exception:
        pass

    # 3) Heuristic: quote bare keys and unquoted string values
    def _quote_keys(s: str) -> str:
        # Insert quotes around bare keys (e.g. {key: -> {"key":)
        return re.sub(r'(?P<prefix>[{,]\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:',
                      lambda m: f"{m.group('prefix')}\"{m.group('key')}\":",
                      s)

    def _quote_values(s: str) -> str:
        # Quote unquoted string-like values after colon, but skip numbers and literals true/false/null
        def repl(m: re.Match) -> str:
            val = m.group('val')
            if re.fullmatch(r'-?\d+(?:\.\d+)?', val) or val in ('true', 'false', 'null'):
                return f": {val}"
            if val.startswith('"') or val.startswith("'"):
                return f": {val}"
            return f": \"{val}\""

        # Allow forward slashes in unquoted values (common in S3 keys)
        return re.sub(r':\s*(?P<val>[A-Za-z_./][A-Za-z0-9_./-]*)', repl, s)

    fixed = _quote_keys(raw)
    fixed = _quote_values(fixed)

    try:
        return json.loads(fixed)
    except Exception as exc:
        raise ValueError(f"Unable to parse event payload after heuristic fixes: {exc}\nRaw: {raw}\nFixed: {fixed}") from exc


def entrypoint(
    argv: List[str],
    db_client: Optional[DatabaseClient] = None,
    s3_client: Optional[S3Client] = None,
    repository: Optional[MonitoringRepository] = None,
    processor: Optional[S3DataQualityProcessor] = None,
) -> int:
    """CLI entrypoint for the S3 data quality job.

    Args:
        argv: CLI arguments (e.g. sys.argv[1:]).
        db_client: Optional DatabaseClient for DI (tests).
        s3_client: Optional S3Client for DI (tests).
        repository: Optional repository for DI (tests).
        processor: Optional processor for DI (tests).

    Returns:
        Exit code (0 success, 1 on error).
    """
    parser = argparse.ArgumentParser(
        prog="file-processing s3_data_quality",
        description="Process S3 objects for data quality validation",
    )

    parser.add_argument(
        "--bucket",
        type=str,
        help="S3 bucket name",
    )
    parser.add_argument(
        "--key",
        type=str,
        help="S3 object key",
    )
    parser.add_argument(
        "--event-json",
        type=str,
        help=(
            "S3 event as JSON string (AWS-style payload). "
            "Accepts AWS Records wrappers (SNS/SQS) or direct {'bucket':..,'key':..} dicts."
        ),
    )
    parser.add_argument(
        "--auto-create",
        action="store_true",
        default=False,
        help="Auto-create monitoring_file if not found (default: False)",
    )
    parser.add_argument(
        "--skip-profile",
        action="store_true",
        help="Skip generating profile payload",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process events but skip writing results to the database",
    )
    parser.add_argument(
        "--dry-run-output",
        type=str,
        help="When --dry-run is set, write JSONL results to this path (default: ./dry_run_results.jsonl)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--run-date",
        type=str,
        help="Override run date (YYYY-MM-DD) to apply to parsed events that lack date information",
    )
    parser.add_argument(
        "--run-hour",
        type=int,
        help="Override run hour (0-23) to apply to parsed events that lack hour information",
    )

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    # Build config
    s3_config = _build_s3_config()

    # Log the effective configuration
    logger.info("Using S3 config: %s", s3_config)

    # Build S3 client
    # DI: prefer provided s3_client
    _s3_client = s3_client or build_s3_client(s3_config)

    # Build events list - only support inline/event-json or bucket+key
    events: List[S3Event] = []

    if args.event_json:
        try:
            payload = _tolerant_parse_event_json(args.event_json)
        except Exception as exc:
            logger.error("Failed to parse --event-json: %s", exc)
            return 1

        try:
            if isinstance(payload, dict):
                events.extend(_extract_s3_events(payload))
            elif isinstance(payload, list):
                events.extend(_extract_s3_events({"Records": payload}))
            elif isinstance(payload, str):
                events.extend(_extract_s3_events(json.loads(payload)))
            else:
                logger.error("Unsupported payload type for --event-json: %s", type(payload))
                return 1
        except Exception as exc:
            logger.error("Failed to extract S3 events from --event-json payload: %s", exc)
            return 1

    elif args.bucket and args.key:
        events.append(S3Event(bucket=args.bucket, key=args.key))

    else:
        parser.error("Must specify --bucket/--key or --event-json (AWS-style payload)")

    logger.info("Events to process: %d", len(events))

    # Build processor with DI
    if processor is None:
        _db = db_client or DatabaseClient()
        repo = repository or MonitoringRepository(_db)

        proc_config = S3DataQualityProcessorConfig(
            auto_create_monitoring_file=args.auto_create,
            generate_profile=not args.skip_profile,
            dry_run=args.dry_run,
            dry_run_output_path=args.dry_run_output,
        )
        processor = S3DataQualityProcessor(
            repository=repo,
            s3_client=_s3_client,
            config=proc_config,
        )

    # Process events
    has_errors = False
    for event in events:
        # Apply overrides to the event parsing if provided #TODO - Why?
        if args.run_date:
            try:
                from datetime import date as _d

                event.override_run_date = datetime.strptime(args.run_date, "%Y-%m-%d").date()
            except Exception:
                logger.warning("Invalid --run-date format, expected YYYY-MM-DD: %s", args.run_date)
        if args.run_hour is not None:
            try:
                event.override_run_hour = int(args.run_hour)
                if not 0 <= event.override_run_hour <= 23:
                    raise ValueError()
            except Exception:
                logger.warning("Invalid --run-hour value, expected 0-23: %s", args.run_hour)

        result = _process_single_event(processor, event)
        _print_result(result)
        if result.get("status") == "error":
            has_errors = True

    return 1 if has_errors else 0


JOB = (entrypoint, "Process S3 objects for data quality validation")
