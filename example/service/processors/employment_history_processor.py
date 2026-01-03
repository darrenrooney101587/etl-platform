import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from service.config.config import EmploymentHistoryConfig
from service.database import client
from service.s3.client import S3Client

logger = logging.getLogger(__name__)


class EmploymentHistoryProcessor(S3Client):
    """Processes employment history data and prepares it for S3 upload.

    This class handles fetching employment history data from the database,
    formatting it as CSV, and uploading it to S3 with proper metadata.

    :param config: Employment history configuration
    :type config: EmploymentHistoryConfig
    :param s3_client: Optional S3 client for dependency injection
    :type s3_client: Optional[Any]
    """

    def __init__(self, config: EmploymentHistoryConfig, s3_client: Optional[Any] = None) -> None:
        """Initialize EmploymentHistoryProcessor with configuration.

        :param config: Employment history configuration
        :type config: EmploymentHistoryConfig
        :param s3_client: Optional S3 client for dependency injection
        :type s3_client: Optional[Any]
        """
        super().__init__(config, s3_client)
        self.data: Optional[List[Dict[str, Any]]] = None
        self.database_client = client.DatabaseClient()

    def fetch_data(self) -> List[Dict[str, Any]]:
        """Fetch employment history data from the database.

        :returns: Employment history records
        :rtype: List[Dict[str, Any]]
        :raises Exception: When database query fails
        """

        try:
            self.data = self.database_client.get_organization_employment_history(self.config.agency_id)
            logger.info(f"Fetched {len(self.data)} employment history records for agency {self.config.agency_id}")
            return self.data
        except Exception as e:
            logger.error(f"Failed to fetch employment history data: {str(e)}")
            raise

    def get_fieldnames(self) -> List[str]:
        """Get the fieldnames for employment history CSV.

        :returns: List of field names for CSV headers
        :rtype: List[str]
        """
        return [
            'display_name',
            'employee_id',
            'effective_date',
            'employment_action',
            'title_rank',
            'employment_type',
            'comment',
            'status',
            'supervisor',
            'tour_of_duty',
            'role'
        ]

    def get_filename(self) -> str:
        """Generate filename for the employment history CSV.

        Note: This method is kept for compatibility but the actual filename
        generation is now handled by the generic upload method.

        :returns: Filename with timestamp
        :rtype: str
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"employment_history_agency_{self.config.agency_id}_{timestamp}.csv"

    def get_summary(self) -> Dict[str, Any]:
        """Get summary information about the processed data.

        :returns: Summary information including record count and metadata
        :rtype: Dict[str, Any]
        """
        if not self.data:
            return {'record_count': 0, 'agency_id': self.config.agency_id}

        return {
            'agency_id': self.config.agency_id,
            'record_count': len(self.data),
            'filename': self.get_filename(),
            'data_fields': [
                'display_name',
                'employee_id',
                'effective_date',
                'employment_action',
                'title_rank',
                'employment_type',
                'status',
                'role'
            ]
        }

    def upload_to_s3(self) -> Dict[str, Any]:
        """Upload employment history CSV to S3.

        :returns: Upload result with status and details
        :rtype: Dict[str, Any]
        """
        # Ensure data is fetched
        if not self.data:
            self.fetch_data()

        # Use the generic upload method from base class
        return self.upload_data_as_csv(
            data=self.data,
            fieldnames=self.get_fieldnames(),
            filename_prefix=f"employment_history_agency_{self.config.agency_id}",
            subfolder="employment_history",
            record_count_key="records_count"
        )
