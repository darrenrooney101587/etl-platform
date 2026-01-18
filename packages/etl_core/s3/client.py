"""Generic S3 client utilities moved into etl_core.

This is a near-copy of the implementation previously in the pipeline processing
package with imports and type references adjusted to reference etl_core.config.S3Config.
"""
from __future__ import annotations

import csv
import io
import logging
import os
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import NoCredentialsError

from etl_core.config.config import S3Config

logger = logging.getLogger(__name__)


class S3Client:
    """Base class for S3 operations.

    This class provides common S3 functionality for uploading CSV files and data.
    It supports dependency injection for the S3 client to enable testing.
    """

    def __init__(self, config: S3Config, s3_client: Optional[Any] = None) -> None:
        self.config = config
        self.s3_client = s3_client or self._initialize_s3_client()

    def _initialize_s3_client(self) -> Any:
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
        if self.config.agency_s3_slug:
            return self.config.agency_s3_slug
        elif hasattr(self.config, 'agency_id') and self.config.agency_id:
            return f"agency-{self.config.agency_id}"
        else:
            return "unknown-agency"

    def upload_csv_to_s3(self, csv_content: str, filename: str, subfolder: str = "") -> Dict[str, Any]:
        try:
            if not csv_content:
                return {
                    'status': 'warning',
                    'message': 'No data to upload'
                }

            agency_folder = self._get_agency_folder()
            if subfolder:
                s3_key = f"{agency_folder}{self.config.destination_prefix.rstrip('/')}/{subfolder}/{filename}"
            else:
                s3_key = f"{agency_folder}{self.config.destination_prefix.rstrip('/')}/{filename}"

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
        try:
            if not data:
                return {
                    'status': 'warning',
                    'message': 'No data to upload'
                }

            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
            writer.writeheader()

            for record in data:
                processed_record = {}
                for key, value in record.items():
                    if isinstance(value, datetime):
                        processed_record[key] = value.isoformat()
                    else:
                        processed_record[key] = value
                writer.writerow(processed_record)

            csv_content = csv_buffer.getvalue()
            csv_buffer.close()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{filename_prefix}_{timestamp}.csv"

            result = self.upload_csv_to_s3(csv_content, filename, subfolder)

            if result['status'] == 'success' and record_count_key:
                result[record_count_key] = len(data)

            return result

        except Exception as e:
            return {'status': 'error', 'message': f'Error uploading data CSV: {str(e)}'}


class LocalS3ObjectBody:
    """File-like body wrapper matching boto3 get_object()['Body']."""

    def __init__(self, data: bytes) -> None:
        self._bio = BytesIO(data)

    def read(self) -> bytes:
        """Read all bytes."""
        return self._bio.read()


class LocalS3BotoClient:
    """Minimal boto3 S3 client shim reading objects from local disk.

    This is intended for local development where we want to run the production
    processing code paths without accessing AWS.

    Mapping rules:
    - LOCAL_S3_ROOT must point to a directory.
    - Requested Key is resolved relative to LOCAL_S3_ROOT.
    """

    def __init__(self, root_dir: str) -> None:
        self._root_dir = root_dir

    def get_object(self, Bucket: str, Key: str) -> Dict[str, Any]:  # noqa: N803
        path = os.path.join(self._root_dir, Key.lstrip("/"))
        if not os.path.exists(path):
            raise FileNotFoundError(f"Local S3 object not found: {path}")

        with open(path, "rb") as f:
            data = f.read()

        return {"Body": LocalS3ObjectBody(data)}


def build_s3_client(config: S3Config) -> "S3Client":
    """Build an S3Client.

    If LOCAL_S3_ROOT is set, the returned S3Client will read objects from disk
    via a small shim that implements boto3's get_object().
    """
    local_root = os.getenv("LOCAL_S3_ROOT")
    if local_root:
        return S3Client(config=config, s3_client=LocalS3BotoClient(local_root))

    return S3Client(config=config)
