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
