"""Job entrypoint for running attachment data quality checks."""
from __future__ import annotations

import argparse
from typing import Any, Dict, List, Optional

from etl_core.database.client import DatabaseClient
from file_processing.processors.data_quality_processor import DataQualityProcessor
from file_processing.repositories.data_quality_repository import DataQualityRepository


def _print_results(result: Dict[str, Any]) -> None:
    """Print results from the data quality run."""
    print(result.get("message", ""))

    metrics = result.get("metrics") or {}
    if metrics:
        print(f"Agency: {metrics.get('agency_id')}")
        print(f"Total files: {metrics.get('total_files')}")
        print(f"Forms: {metrics.get('forms')}")
        print(f"User documents: {metrics.get('user_documents')}")
        print(f"Missing output filenames: {metrics.get('missing_output_filenames')}")

    issues = result.get("issues") or []
    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"- {issue.get('type')}: {issue.get('count')}")
            examples = issue.get("examples") or []
            if examples:
                print(f"  examples: {', '.join([str(e) for e in examples])}")


def entrypoint(argv: List[str], db_client: Optional[DatabaseClient] = None) -> int:
    """CLI entrypoint for the data quality job."""
    parser = argparse.ArgumentParser(
        prog="file-processing data-quality",
        description="Run data quality checks against attachment metadata",
    )
    parser.add_argument(
        "--agency-id",
        required=True,
        type=int,
        help="Agency ID to run checks against",
    )
    args = parser.parse_args(argv)

    repository = DataQualityRepository(db_client or DatabaseClient())
    processor = DataQualityProcessor(repository)

    result = processor.run_checks(args.agency_id)
    _print_results(result)

    if result.get("status") == "error":
        return 1
    return 0


JOB = (entrypoint, "Run data quality checks for attachments")
