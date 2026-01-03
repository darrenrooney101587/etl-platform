"""
Service layer for S3 file processing operations.

This module encapsulates the business logic for processing S3 files and employment
history data, making it reusable across different interfaces (management commands, API endpoints).
"""
import logging
from typing import Any, Dict, Optional

from service.config.factory import create_employment_history_processor, create_s3_processor
from service.database.client import DatabaseClient

logger = logging.getLogger(__name__)

class ServiceHandler:
    """Service class that handles S3 file processing operations."""

    def __init__(self,
                 source_bucket: str,
                 destination_bucket: str):
        """Initialize the S3 processing service.

        :param source_bucket: Source S3 bucket name
        :type source_bucket: str
        :param destination_bucket: Destination S3 bucket name
        :type destination_bucket: str
        :param progress_callback: Optional progress callback function
        :type progress_callback: Optional[Callable]
        :param db_client: Optional database client to inject for testability
        :type db_client: Optional[DatabaseClient]
        """
        self.source_bucket = source_bucket
        self.destination_bucket = destination_bucket
        self.db = DatabaseClient(db_alias='bms')

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
            db_results = self.db.get_attachment_files_for_s3_processing(agency_id)
            forms = [f for f in db_results if f['attachable_type'] == 'Form']
            user_docs = [f for f in db_results if f['attachable_type'] == 'UserDocument']
            total_size_mb = sum(f.get('byte_size', 0) for f in db_results) / 1024 / 1024

            # Analyze employment history (read-only)
            employment_count = 0
            try:
                employment_processor = create_employment_history_processor(
                    agency_id=agency_id,
                    destination_bucket=self.destination_bucket,
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
            db_results = self.db.get_attachment_files_for_s3_processing(agency_id)
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
                processor = create_s3_processor(
                    source_bucket=self.source_bucket,
                    destination_bucket=self.destination_bucket,
                    agency_s3_slug=agency_s3_slug,
                    agency_id=agency_id,
                    destination_prefix='/downloads/'
                )

                # Process files (concurrent processing enabled)
                file_results = processor.process_files(
                    file_mappings=db_results,
                    concurrent=True
                )

                # Upload metadata CSV
                csv_result = processor.upload_metadata_csv(db_results)

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
                    employment_processor = create_employment_history_processor(
                        agency_id=agency_id,
                        destination_bucket=self.destination_bucket,
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
            employment_processor = create_employment_history_processor(
                agency_id=agency_id,
                destination_bucket=self.destination_bucket,
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
