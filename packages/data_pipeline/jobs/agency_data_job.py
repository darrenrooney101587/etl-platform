"""
Job logic for processing Agency Data (S3 files and Employment History).

This module encapsulates the business logic for processing S3 files and employment
history data, making it reusable across different interfaces (management commands, API endpoints).
"""
import argparse
import logging
import sys
import traceback
from typing import Any, Dict, List, Optional

from etl_core.database.client import DatabaseClient
from etl_core.config.config import EmploymentHistoryConfig, S3Config
from data_pipeline.processors.employment_history_processor import EmploymentHistoryProcessor
from data_pipeline.shared.s3_adapter import get_configured_processor, upload_attachment_manifest
from data_pipeline.repositories.attachment_repository import AttachmentRepository

logger = logging.getLogger(__name__)


def _print_results(result: Dict[str, Any]) -> None:
    """Print the results returned by AgencyDataJob in a human-friendly format."""
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


def entrypoint(argv: List[str]) -> int:
    """CLI entrypoint for Agency Data Job."""
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
        service = AgencyDataJob(source_bucket=args.source_bucket, destination_bucket=args.destination_bucket)
        result = service.process_agency_files(args.agency_id)
        _print_results(result)

        if result.get('status') == 'error':
            return 2
        return 0

    except Exception as exc:
        print(f"Error during processing: {exc}")
        traceback.print_exc()
        return 1


class AgencyDataJob:
    """Job class that handles S3 file processing operations for an agency."""

    def __init__(self,
                 source_bucket: str,
                 destination_bucket: str,
                 db_client: Optional[DatabaseClient] = None):
        """Initialize the S3 processing service.

        :param source_bucket: Source S3 bucket name
        :type source_bucket: str
        :param destination_bucket: Destination S3 bucket name
        :type destination_bucket: str
        :param db_client: Optional DatabaseClient for DI/testing
        :type db_client: Optional[DatabaseClient]
        """
        self.source_bucket = source_bucket
        self.destination_bucket = destination_bucket
        self.db = db_client or DatabaseClient()
        self.attachment_repo = AttachmentRepository(self.db)

    def analyze_agency_data(self, agency_id: int, dry_run: bool = False) -> Dict[str, Any]:
        """Analyze agency data without performing any external operations.

        :param agency_id: Agency ID to analyze
        :type agency_id: int
        :param dry_run: When True, do not invoke any external side effects (reads only)
        :type dry_run: bool
        :return: Analysis results
        :rtype: Dict[str, Any]
        """
        try:
            # Get agency info
            agency_s3_slug = self.db.get_agency_s3_slug(agency_id)
            folder_name = agency_s3_slug if agency_s3_slug else f"agency-{agency_id}"

            # Analyze files (read-only)
            db_results = self.attachment_repo.get_attachment_files_for_s3_processing(agency_id)
            forms = [f for f in db_results if f['attachable_type'] == 'Form']
            user_docs = [f for f in db_results if f['attachable_type'] == 'UserDocument']
            total_size_mb = sum(f.get('byte_size', 0) for f in db_results) / 1024 / 1024

            # Analyze employment history (read-only)
            employment_count = 0
            try:
                employment_processor = self._create_employment_history_processor(
                    agency_id=agency_id,
                    agency_s3_slug=agency_s3_slug,
                    destination_prefix='/downloads/'
                )
                employment_data = employment_processor.fetch_data()
                employment_count = len(employment_data)
            except Exception:
                # Ignore employment history errors during analysis, keep counts zero
                employment_count = 0

            return {
                'status': 'success',
                'agency_id': agency_id,
                'agency_s3_slug': agency_s3_slug,
                'folder_name': folder_name,
                'files': {
                    'total': len(db_results),
                    'forms': len(forms),
                    'user_documents': len(user_docs),
                    'total_size_mb': round(total_size_mb, 1)
                },
                'employment_records': employment_count,
                'has_operations': len(db_results) > 0 or employment_count > 0,
                'dry_run': bool(dry_run),
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Error analyzing agency data: {str(e)}'
            }

    def process_agency_files(self, agency_id: int, dry_run: bool = False) -> Dict[str, Any]:
        """Process S3 files and employment history for an agency.

        :param agency_id: Agency ID to process
        :type agency_id: int
        :param dry_run: When True, only read data and compute planned operations; no external side effects
        :type dry_run: bool
        :return: Processing results
        :rtype: Dict[str, Any]
        """
        try:
            # Read-only inputs
            db_results = self.attachment_repo.get_attachment_files_for_s3_processing(agency_id)
            agency_s3_slug = self.db.get_agency_s3_slug(agency_id)

            if not dry_run:
                if not db_results:
                    return {
                        'status': 'warning',
                        'message': 'No files found in database for processing',
                        'results': {
                            'files_processed': 0,
                            'files_successful': 0,
                            'files_failed': 0,
                            'failed_files': [],
                            'csv_upload': None,
                            'employment_history': None
                        }
                    }

                # Create processor
                processor = self._create_s3_processor(
                    agency_id=agency_id,
                    agency_s3_slug=agency_s3_slug,
                    destination_prefix='/downloads/'
                )

                # Process files (concurrent processing enabled)
                file_results = processor.process_files(
                    file_mappings=db_results,
                    concurrent=True
                )

                # Upload metadata CSV
                csv_result = upload_attachment_manifest(processor, db_results)

                # Process employment history
                employment_result = self._process_employment_history(
                    agency_id, agency_s3_slug
                )

                # Summarize results
                successful_files = [r for r in file_results if r['status'] == 'success']
                failed_files = [r for r in file_results if r['status'] != 'success']

                return {
                    'status': 'success',
                    'message': f'Processing completed for agency {agency_id}',
                    'results': {
                        'files_processed': len(file_results),
                        'files_successful': len(successful_files),
                        'files_failed': len(failed_files),
                        'failed_files': [{'source_key': f['source_key'], 'message': f['message']}
                                       for f in failed_files],
                        'csv_upload': csv_result,
                        'employment_history': employment_result
                    }
                }
            else:
                # Dry run: Compute planned steps without performing external actions
                files_planned = len(db_results)
                try:
                    employment_processor = self._create_employment_history_processor(
                        agency_id=agency_id,
                        agency_s3_slug=agency_s3_slug,
                        destination_prefix='/downloads/'
                    )
                    employment_data = employment_processor.fetch_data()
                    employment_records = len(employment_data)
                except Exception:
                    employment_records = 0

                return {
                    'status': 'success',
                    'message': f'Dry run: no external actions executed for agency {agency_id}',
                    'dry_run': True,
                    'results': {
                        'files_planned': files_planned,
                        'csv_upload_planned': files_planned > 0,
                        'employment_records': employment_records,
                        'files_processed': 0,
                        'files_successful': 0,
                        'files_failed': 0,
                        'failed_files': [],
                        'csv_upload': None,
                        'employment_history': None,
                    },
                }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Error during S3 processing: {str(e)}'
            }

    def _process_employment_history(self, agency_id: int, agency_s3_slug: str) -> Dict[str, Any]:
        """Process employment history data for an agency.

        :param agency_id: Agency ID
        :type agency_id: int
        :param agency_s3_slug: Agency S3 slug
        :type agency_s3_slug: str
        :return: Employment history processing result
        :rtype: Dict[str, Any]
        """
        try:
            employment_processor = self._create_employment_history_processor(
                agency_id=agency_id,
                agency_s3_slug=agency_s3_slug,
                destination_prefix='/downloads/'
            )

            employment_data = employment_processor.fetch_data()

            if employment_data:
                employment_result = employment_processor.upload_to_s3()
                employment_result['records_count'] = len(employment_data)
                return employment_result
            else:
                return {
                    'status': 'warning',
                    'message': 'No employment history data found for this agency',
                    'records_count': 0
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Error processing employment history: {str(e)}',
                'records_count': 0
            }

    def _create_s3_processor(self, agency_id: int, agency_s3_slug: str, destination_prefix: str):
        config = S3Config(
            source_bucket=self.source_bucket,
            destination_bucket=self.destination_bucket,
            agency_s3_slug=agency_s3_slug,
            agency_id=agency_id,
            destination_prefix=destination_prefix
        )
        # Use the adapter to get a configured processor
        return get_configured_processor(config, agency_id=str(agency_id))

    def _create_employment_history_processor(self, agency_id: int, agency_s3_slug: str, destination_prefix: str):
        config = EmploymentHistoryConfig(
            agency_id=agency_id,
            destination_bucket=self.destination_bucket,
            agency_s3_slug=agency_s3_slug,
            destination_prefix=destination_prefix
        )
        return EmploymentHistoryProcessor(config)


# Expose JOB as a lightweight tuple (entrypoint, description) to avoid importing registry types here
JOB = (entrypoint, (__doc__ or "Agency data processing job").strip().splitlines()[0])
