import csv
import io
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Union

import boto3
from botocore.exceptions import NoCredentialsError

from service.config.config import S3Config, EmploymentHistoryConfig

logger = logging.getLogger(__name__)


class S3Client:
    """Base class for S3 operations.

    This class provides common S3 functionality for uploading CSV files and data.
    It supports dependency injection for the S3 client to enable testing.

    :param config: Configuration object containing S3 settings
    :type config: Union[S3Config, EmploymentHistoryConfig]
    :param s3_client: Optional S3 client for dependency injection
    :type s3_client: Optional[boto3.client]
    """

    def __init__(self, config: Union['S3Config', 'EmploymentHistoryConfig'], s3_client: Optional[Any] = None) -> None:
        """Initialize S3Client with configuration and optional S3 client.

        :param config: Configuration object containing S3 settings
        :type config: Union[S3Config, EmploymentHistoryConfig]
        :param s3_client: Optional S3 client for dependency injection
        :type s3_client: Optional[boto3.client]
        """
        self.config = config
        self.s3_client = s3_client or self._initialize_s3_client()

    def _initialize_s3_client(self) -> Any:
        """Initialize the S3 client with provided credentials.

        :returns: Configured boto3 S3 client
        :rtype: boto3.client
        :raises NoCredentialsError: When AWS credentials are not found
        """
        try:
            if self.config.aws_access_key_id and self.config.aws_secret_access_key:
                return boto3.client(
                    's3',
                    aws_access_key_id=self.config.aws_access_key_id,
                    aws_secret_access_key=self.config.aws_secret_access_key,
                    region_name=self.config.aws_region
                )
            else:
                return boto3.client('s3', region_name=self.config.aws_region)
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise

    def _get_agency_folder(self) -> str:
        """Get the agency folder name based on slug or ID.

        :returns: Agency folder name for S3 key construction
        :rtype: str
        """
        if self.config.agency_s3_slug:
            return self.config.agency_s3_slug
        elif hasattr(self.config, 'agency_id') and self.config.agency_id:
            return f"agency-{self.config.agency_id}"
        else:
            return "unknown-agency"

    def upload_csv_to_s3(self, csv_content: str, filename: str, subfolder: str = "") -> Dict[str, Any]:
        """Generic method to upload CSV content to S3.

        :param csv_content: CSV content as string
        :type csv_content: str
        :param filename: Name of the file to create
        :type filename: str
        :param subfolder: Optional subfolder (e.g., 'employment_history', 'attachment_manifest')
        :type subfolder: str
        :returns: Upload result with status and details
        :rtype: Dict[str, Any]
        """
        try:
            if not csv_content:
                return {
                    'status': 'warning',
                    'message': 'No data to upload'
                }

            # Build S3 key
            agency_folder = self._get_agency_folder()
            if subfolder:
                s3_key = f"{agency_folder}{self.config.destination_prefix.rstrip('/')}/{subfolder}/{filename}"
            else:
                s3_key = f"{agency_folder}{self.config.destination_prefix.rstrip('/')}/{filename}"

            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.config.destination_bucket,
                Key=s3_key,
                Body=csv_content.encode('utf-8'),
                ContentType='text/csv'
            )

            return {
                'status': 'success',
                'message': f'Successfully uploaded CSV to {self.config.destination_bucket}/{s3_key}',
                's3_key': s3_key,
                'file_size': len(csv_content.encode('utf-8')),
                'filename': filename
            }

        except Exception as e:
            return {'status': 'error', 'message': f'Error uploading CSV: {str(e)}'}

    def upload_data_as_csv(self, data: List[Dict[str, Any]], fieldnames: List[str],
                          filename_prefix: str, subfolder: str = "",
                          record_count_key: Optional[str] = None) -> Dict[str, Any]:
        """Generic method to convert data to CSV and upload to S3.

        :param data: List of dictionaries to convert to CSV
        :type data: List[Dict[str, Any]]
        :param fieldnames: List of field names for CSV headers
        :type fieldnames: List[str]
        :param filename_prefix: Prefix for the generated filename (timestamp will be added)
        :type filename_prefix: str
        :param subfolder: Optional subfolder for S3 key
        :type subfolder: str
        :param record_count_key: If provided, the key name to include record count in result
        :type record_count_key: Optional[str]
        :returns: Upload result with status and details
        :rtype: Dict[str, Any]
        """

        try:
            if not data:
                return {
                    'status': 'warning',
                    'message': 'No data to upload'
                }

            # Generate CSV content
            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
            writer.writeheader()

            for record in data:
                # Convert any datetime objects to strings
                processed_record = {}
                for key, value in record.items():
                    if isinstance(value, datetime):
                        processed_record[key] = value.isoformat()
                    else:
                        processed_record[key] = value
                writer.writerow(processed_record)

            csv_content = csv_buffer.getvalue()
            csv_buffer.close()

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{filename_prefix}_{timestamp}.csv"

            # Upload CSV content
            result = self.upload_csv_to_s3(csv_content, filename, subfolder)

            # Add record count to result if successful
            if result['status'] == 'success' and record_count_key:
                result[record_count_key] = len(data)

            return result

        except Exception as e:
            return {'status': 'error', 'message': f'Error uploading data CSV: {str(e)}'}
