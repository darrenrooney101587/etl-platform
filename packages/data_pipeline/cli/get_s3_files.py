"""CLI entrypoint to process S3 files and employment history.

This replaces the legacy Django management command. It is intended to be
installed as a console script (`data-pipeline-get-s3-files`) and used in
non-Django environments (containers, EKS jobs, CI).
"""
from __future__ import annotations

import argparse
import sys
import traceback
from typing import Any, Dict, List, Optional

from packages.data_pipeline.service_handler import ServiceHandler


def _print_results(result: Dict[str, Any]) -> None:
    """Print the results returned by ServiceHandler in a human-friendly format."""
    if result.get("status") in ("error", "warning"):
        print(f"{result.get('status').upper()}: {result.get('message')}")
        return

    results_data = result.get("results", {})
    print(f"Processing completed: {result.get('message')}")
    print(f"Files processed: {results_data.get('files_processed')}")
    print(f"Files successful: {results_data.get('files_successful')}")
    print(f"Files failed: {results_data.get('files_failed')}")

    failed = results_data.get('failed_files') or []
    if failed:
        print("Failed files:")
        for f in failed:
            print(f"  - {f.get('source_key')}: {f.get('message')}")

    csv_res = results_data.get('csv_upload')
    if csv_res:
        status = "success" if csv_res.get('status') == 'success' else 'error'
        print(f"Metadata CSV: {status} {csv_res.get('message', '')}")

    emp = results_data.get('employment_history')
    if emp:
        status = (
            "success" if emp.get('status') == 'success' else
            "error" if emp.get('status') == 'error' else
            "warning"
        )
        print(f"Employment History: {status} {emp.get('message', '')}")
        if emp.get('status') == 'success':
            print(f"  Records: {emp.get('records_count', 0)}")


def main(argv: Optional[List[str]] = None) -> int:
    """CLI main function.

    Args:
        argv: List of command-line arguments (defaults to sys.argv[1:]).

    Returns:
        An exit code integer (0 for success, non-zero for error).
    """
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(description="Process S3 files and employment history for an agency")
    parser.add_argument("--agency-id", type=int, default=10, help="Agency ID to filter by (default: 10)")
    parser.add_argument(
        "--source-bucket",
        type=str,
        default="benchmarkanalytics-production-env-userdocument-test",
        help="Source S3 bucket name"
    )
    parser.add_argument(
        "--destination-bucket",
        type=str,
        default="etl-ba-research-client-etl",
        help="Destination S3 bucket name"
    )

    args = parser.parse_args(argv)

    try:
        service = ServiceHandler(source_bucket=args.source_bucket, destination_bucket=args.destination_bucket)
        result = service.process_agency_files(args.agency_id)
        _print_results(result)

        # Consider non-zero on explicit error status
        if result.get('status') == 'error':
            return 2
        return 0

    except Exception as exc:  # pragma: no cover - surface unexpected errors
        print(f"Error during processing: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
