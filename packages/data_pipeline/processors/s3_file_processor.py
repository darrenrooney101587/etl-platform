import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional
from botocore.exceptions import ClientError

from packages.data_pipeline.config.config import S3Config
from packages.data_pipeline.s3.client import S3Client

logger = logging.getLogger(__name__)


class S3FileProcessor(S3Client):
    """Simplified S3 file processor for copying files between buckets.

    This class provides functionality for copying files between S3 buckets with
    retry logic, progress tracking, and metadata upload capabilities.

    :param config: S3 configuration settings
    :type config: S3Config
    :param s3_client: Optional S3 client for dependency injection
    :type s3_client: Optional[Any]
    """

    def __init__(self, config: S3Config, s3_client: Optional[Any] = None) -> None:
        """Initialize S3FileProcessor with configuration.

        :param config: S3 configuration settings
        :type config: S3Config
        :param s3_client: Optional S3 client for dependency injection
        :type s3_client: Optional[Any]
        """
        super().__init__(config, s3_client)
        self._progress_callback: Optional[Callable[[int, int, str], None]] = None

    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        """Set a callback function to receive progress updates.

        :param callback: Function that accepts (completed, total, current_file)
        :type callback: Callable[[int, int, str], None]
        """
        self._progress_callback = callback

    def process_files(self, file_mappings: List[Dict[str, Any]], concurrent: bool = True) -> List[Dict[str, Any]]:
        """Process multiple files concurrently.

        Note: concurrent parameter is kept for backward compatibility but is ignored.
        All processing is done concurrently by default.

        :param file_mappings: List of file mapping dictionaries
        :type file_mappings: List[Dict[str, Any]]
        :param concurrent: Legacy parameter for compatibility (ignored)
        :type concurrent: bool
        :returns: List of results compatible with original function format
        :rtype: List[Dict[str, Any]]
        """
        results = []
        completed = 0

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
                    self._progress_callback(completed, len(file_mappings), mapping.get('filename'))

        return results

    def _copy_single_file(self, mapping: Dict[str, Any]) -> Dict[str, Any]:
        """Copy a single file with retry logic.

        :param mapping: File mapping dictionary with source and destination info
        :type mapping: Dict[str, Any]
        :returns: Result dictionary with status and details
        :rtype: Dict[str, Any]
        """
        source_key = mapping.get('filename', '')
        output_filename = mapping.get('output_filename', '')

        if not source_key or not output_filename:
            return {
                'source_key': source_key,
                'destination_key': None,
                'status': 'error',
                'message': 'Missing filename or output_filename in mapping'
            }

        # Use inherited method to get agency folder
        agency_folder = self._get_agency_folder()
        destination_key = f"{agency_folder}{self.config.destination_prefix.rstrip('/')}/{output_filename}"

        # Retry logic
        for attempt in range(1, self.config.retry_attempts + 1):
            try:
                # Check source file exists
                response = self.s3_client.head_object(
                    Bucket=self.config.source_bucket,
                    Key=source_key
                )
                file_size = response['ContentLength']

                # Copy file
                copy_source = {'Bucket': self.config.source_bucket, 'Key': source_key}
                self.s3_client.copy_object(
                    CopySource=copy_source,
                    Bucket=self.config.destination_bucket,
                    Key=destination_key
                )

                return {
                    'source_key': source_key,
                    'destination_key': destination_key,
                    'status': 'success',
                    'message': f'Successfully copied {source_key} to {destination_key}',
                    'file_size': file_size
                }

            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code in ['NoSuchKey', '404']:
                    return {
                        'source_key': source_key,
                        'destination_key': destination_key,
                        'status': 'not_found',
                        'message': f'File not found: {source_key}'
                    }
                else:
                    if attempt < self.config.retry_attempts:
                        time.sleep(attempt)  # Simple backoff
                        continue
                    return {
                        'source_key': source_key,
                        'destination_key': destination_key,
                        'status': 'error',
                        'message': f'AWS error ({error_code}): {e.response["Error"]["Message"]}'
                    }
            except Exception as e:
                if attempt < self.config.retry_attempts:
                    time.sleep(attempt)
                    continue
                return {
                    'source_key': source_key,
                    'destination_key': destination_key,
                    'status': 'error',
                    'message': f'Unexpected error: {str(e)}'
                }

    def upload_metadata_csv(self, query_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Upload query results as metadata CSV to S3.

        :param query_results: List of query result dictionaries
        :type query_results: List[Dict[str, Any]]
        :returns: Upload result with status and details
        :rtype: Dict[str, Any]
        """
        if not query_results:
            return {'status': 'error', 'message': 'No query results to upload'}

        # Use the generic upload method from base class
        fieldnames = list(query_results[0].keys())
        return self.upload_data_as_csv(
            data=query_results,
            fieldnames=fieldnames,
            filename_prefix="metadata",
            subfolder="attachment_manifest",
            record_count_key="records_count"
        )
