from typing import Any, Dict

from django.core.management.base import BaseCommand

from service.service_handler import ServiceHandler

class Command(BaseCommand):
    """Django management command for processing S3 files and employment history.
    
    This command handles file copying operations and employment history data
    processing for agencies.
    """
    help = 'Execute get_attachment_files_for_s3_processing function and display results'

    def add_arguments(self, parser: Any) -> None:
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

    def handle(self, *args: Any, **options: Dict[str, Any]) -> None:
        """Handle the management command execution.

        :param args: Positional arguments
        :type args: Any
        :param options: Command options dictionary
        :type options: Dict[str, Any]
        """
        agency_id = options['agency_id']

        # Create service instance
        service = ServiceHandler(
            source_bucket=options['source_bucket'],
            destination_bucket=options['destination_bucket']
        )
        
        # Process files and employment history
        self._handle_copy(service, agency_id)

    def _handle_copy(self, service: ServiceHandler, agency_id: int) -> None:
        """Handle file copying using the ServiceHandler.

        :param service: ServiceHandler instance
        :type service: ServiceHandler
        :param agency_id: Agency ID to process
        :type agency_id: int
        """
        self.stdout.write(
            self.style.SUCCESS(f'Using ServiceHandler for agency_id={agency_id}...')
        )

        try:
            result = service.process_agency_files(agency_id)

            if result['status'] == 'error':
                self.stdout.write(self.style.ERROR(result['message']))
                return
            elif result['status'] == 'warning':
                self.stdout.write(self.style.WARNING(result['message']))
                return

            # Display results
            results_data = result['results']
            self.stdout.write(f"\nProcessing completed: {result['message']}")
            self.stdout.write(f"Files processed: {results_data['files_processed']}")
            self.stdout.write(f"Files successful: {results_data['files_successful']}")
            self.stdout.write(f"Files failed: {results_data['files_failed']}")

            if results_data['failed_files']:
                self.stdout.write(self.style.WARNING(f'Failed files:'))
                for failed_file in results_data['failed_files']:
                    self.stdout.write(f"  - {failed_file['source_key']}: {failed_file['message']}")

            # CSV upload result
            if results_data['csv_upload']:
                csv_result = results_data['csv_upload']
                status = "success" if csv_result['status'] == 'success' else 'error'
                self.stdout.write(f'Metadata CSV: {status} {csv_result.get("message", "")}')

            # Employment history result
            if results_data['employment_history']:
                emp_result = results_data['employment_history']
                status = "success" if emp_result['status'] == 'success' else "error" if emp_result['status'] == 'error' else "warning"
                self.stdout.write(f'Employment History: {status} {emp_result.get("message", "")}')
                if emp_result['status'] == 'success':
                    self.stdout.write(f'  Records: {emp_result.get("records_count", 0)}')

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during S3 operation: {str(e)}')
            )
            import traceback
            self.stdout.write(traceback.format_exc())
