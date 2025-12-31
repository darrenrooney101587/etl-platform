import argparse
import logging
import sys
from typing import Any, Dict

from data_pipeline.service_handler import ServiceHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main() -> None:
    """Execute get_attachment_files_for_s3_processing function and display results."""
    parser = argparse.ArgumentParser(
        description='Execute get_attachment_files_for_s3_processing function and display results'
    )
    parser.add_argument(
        '--agency-id',
        type=int,
        default=10,
        help='Agency ID to filter by (default: 10)'
    )
    parser.add_argument(
        '--source-bucket',
        type=str,
        default='benchmarkanalytics-production-env-userdocument-test',
        help='Source S3 bucket name (default: benchmarkanalytics-production-env-userdocument-test)'
    )
    parser.add_argument(
        '--destination-bucket',
        type=str,
        default='etl-ba-research-client-etl',
        help='Destination S3 bucket name (default: etl-ba-research-client-etl)'
    )

    args = parser.parse_args()

    handle(args.agency_id, args.source_bucket, args.destination_bucket)

def handle(agency_id: int, source_bucket: str, destination_bucket: str) -> None:
    """Handle the command execution.

    :param agency_id: Agency ID to process
    :param source_bucket: Source S3 bucket name
    :param destination_bucket: Destination S3 bucket name
    """
    # Create service instance
    service = ServiceHandler(
        source_bucket=source_bucket,
        destination_bucket=destination_bucket
    )

    # Process files and employment history
    _handle_copy(service, agency_id)

def _handle_copy(service: ServiceHandler, agency_id: int) -> None:
    """Handle file copying using the ServiceHandler.

    :param service: ServiceHandler instance
    :param agency_id: Agency ID to process
    """
    print(f'Using ServiceHandler for agency_id={agency_id}...')

    try:
        result = service.process_agency_files(agency_id)

        if result['status'] == 'error':
            print(f"ERROR: {result['message']}", file=sys.stderr)
            return
        elif result['status'] == 'warning':
            print(f"WARNING: {result['message']}")
            return

        # Display results
        results_data = result['results']
        print(f"\nProcessing completed: {result['message']}")
        print(f"Files processed: {results_data['files_processed']}")
        print(f"Files successful: {results_data['files_successful']}")
        print(f"Files failed: {results_data['files_failed']}")

        if results_data['failed_files']:
            print('Failed files:')
            for failed_file in results_data['failed_files']:
                print(f"  - {failed_file['source_key']}: {failed_file['message']}")

        # CSV upload result
        if results_data['csv_upload']:
            csv_result = results_data['csv_upload']
            status = "success" if csv_result['status'] == 'success' else 'error'
            print(f'Metadata CSV: {status} {csv_result.get("message", "")}')

        # Employment history result
        if results_data['employment_history']:
            emp_result = results_data['employment_history']
            status = "success" if emp_result['status'] == 'success' else "error" if emp_result['status'] == 'error' else "warning"
            print(f'Employment History: {status} {emp_result.get("message", "")}')
            if emp_result['status'] == 'success':
                print(f'  Records: {emp_result.get("records_count", 0)}')

    except Exception as e:
        print(f"Unexpected error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
