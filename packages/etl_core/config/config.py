"""Core configuration dataclasses for generic ETL components."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class S3Config:
    """Configuration for S3 operations.

    Generic configuration suitable for the core S3 utilities.
    """
    source_bucket: str
    destination_bucket: str
    agency_s3_slug: str
    agency_id: Optional[int] = None
    destination_prefix: str = "/downloads/"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = 'us-gov-west-1'
    max_workers: int = 5
    retry_attempts: int = 3


@dataclass
class EmploymentHistoryConfig:
    """Configuration for employment history operations.

    This dataclass holds configuration parameters specifically for employment history
    data processing and S3 upload operations.

    :param agency_id: Agency ID for database queries
    :type agency_id: int
    :param destination_bucket: Destination S3 bucket name
    :type destination_bucket: str
    :param agency_s3_slug: Agency slug for S3 key construction
    :type agency_s3_slug: str
    :param destination_prefix: Prefix for destination S3 keys
    :type destination_prefix: str
    :param aws_access_key_id: Optional AWS access key ID
    :type aws_access_key_id: Optional[str]
    :param aws_secret_access_key: Optional AWS secret access key
    :type aws_secret_access_key: Optional[str]
    :param aws_region: AWS region for S3 operations
    :type aws_region: str
    """
    agency_id: int
    destination_bucket: str
    agency_s3_slug: str
    destination_prefix: str = "/downloads/"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = 'us-gov-west-1'
