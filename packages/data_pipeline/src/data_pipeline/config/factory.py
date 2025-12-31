"""Factory functions for constructing processing components.

This module provides typed factory helpers to build configured instances of
S3FileProcessor and EmploymentHistoryProcessor according to environment
settings and provided parameters.
"""


import os
from typing import Optional

from data_pipeline.config.config import EmploymentHistoryConfig, S3Config
from data_pipeline.processors.employment_history_processor import EmploymentHistoryProcessor
from data_pipeline.processors.s3_file_processor import S3FileProcessor


def create_s3_processor(
    source_bucket: str,
    destination_bucket: str,
    agency_s3_slug: str,
    agency_id: Optional[int] = None,
    destination_prefix: str = "/downloads/",
    max_workers: int = 5,
    retry_attempts: int = 3,
) -> S3FileProcessor:
    """Create an S3FileProcessor with configuration.

    :param source_bucket: Source S3 bucket name.
    :type source_bucket: str
    :param destination_bucket: Destination S3 bucket name.
    :type destination_bucket: str
    :param agency_s3_slug: Agency slug for S3 key construction.
    :type agency_s3_slug: str
    :param agency_id: Optional agency ID used for fallback folder naming.
    :type agency_id: Optional[int]
    :param destination_prefix: Prefix for destination S3 keys.
    :type destination_prefix: str
    :param max_workers: Maximum number of worker threads.
    :type max_workers: int
    :param retry_attempts: Number of retry attempts for failed operations.
    :type retry_attempts: int
    :returns: Configured S3FileProcessor instance.
    :rtype: S3FileProcessor
    """
    config = S3Config(
        source_bucket=source_bucket,
        agency_s3_slug=agency_s3_slug,
        agency_id=agency_id,
        destination_bucket=destination_bucket,
        destination_prefix=destination_prefix,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_region=os.getenv("AWS_DEFAULT_REGION", "us-gov-west-1"),
        max_workers=max_workers,
        retry_attempts=retry_attempts,
    )

    return S3FileProcessor(config)


def create_employment_history_processor(
    agency_id: int,
    destination_bucket: str,
    agency_s3_slug: str,
    destination_prefix: str = "/downloads/",
) -> EmploymentHistoryProcessor:
    """Create an EmploymentHistoryProcessor with configuration.

    :param agency_id: Agency ID for database queries.
    :type agency_id: int
    :param destination_bucket: Destination S3 bucket name.
    :type destination_bucket: str
    :param agency_s3_slug: Agency slug for S3 key construction.
    :type agency_s3_slug: str
    :param destination_prefix: Prefix for destination S3 keys.
    :type destination_prefix: str
    :returns: Configured EmploymentHistoryProcessor instance.
    :rtype: EmploymentHistoryProcessor
    """
    config = EmploymentHistoryConfig(
        agency_id=agency_id,
        destination_bucket=destination_bucket,
        agency_s3_slug=agency_s3_slug,
        destination_prefix=destination_prefix,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_region=os.getenv("AWS_DEFAULT_REGION", "us-gov-west-1"),
    )

    return EmploymentHistoryProcessor(config)
