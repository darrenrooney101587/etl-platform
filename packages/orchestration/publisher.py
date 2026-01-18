"""S3 Publisher for Airflow DAG files.

This module handles uploading DAG files to S3 with proper validation and
guardrails to prevent cross-package overwrites.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger(__name__)


class DAGPublisher:
    """Publishes DAG files to S3 with validation and safety checks."""

    def __init__(
        self,
        bucket: str,
        environment: str,
        package_name: str,
        aws_region: str = "us-gov-west-1",
        s3_client: Optional[object] = None,
    ):
        """Initialize the DAG publisher.

        Args:
            bucket: S3 bucket name for DAGs.
            environment: Environment name (dev, staging, prod).
            package_name: Name of the package publishing DAGs.
            aws_region: AWS region.
            s3_client: Optional boto3 S3 client (for testing).
        """
        self.bucket = bucket
        self.environment = environment
        self.package_name = package_name
        self.aws_region = aws_region
        self.s3_client = s3_client or boto3.client("s3", region_name=aws_region)

        self._validate_inputs()

    def _validate_inputs(self) -> None:
        """Validate initialization parameters."""
        if not self.bucket:
            raise ValueError("bucket cannot be empty")
        if not self.environment:
            raise ValueError("environment cannot be empty")
        if not self.package_name:
            raise ValueError("package_name cannot be empty")

        # Validate environment
        valid_envs = ["dev", "staging", "prod"]
        if self.environment not in valid_envs:
            raise ValueError(
                f"environment must be one of {valid_envs}, got '{self.environment}'"
            )

        # Validate package name (alphanumeric and underscore only)
        if not self.package_name.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                f"package_name must be alphanumeric (underscore/hyphen allowed), "
                f"got '{self.package_name}'"
            )

    def get_package_prefix(self) -> str:
        """Get the S3 prefix for this package.

        Returns:
            S3 prefix in the format: <env>/<package_name>/
        """
        return f"{self.environment}/{self.package_name}/"

    def verify_bucket_exists(self) -> bool:
        """Verify that the S3 bucket exists and is accessible.

        Returns:
            True if bucket exists, False otherwise.
        """
        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
            logger.info("Verified bucket exists: %s", self.bucket)
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "404":
                logger.error("Bucket does not exist: %s", self.bucket)
            else:
                logger.error("Cannot access bucket %s: %s", self.bucket, e)
            return False

    def publish_dag_file(
        self,
        local_path: Path,
        dag_filename: Optional[str] = None,
    ) -> str:
        """Publish a single DAG file to S3.

        Args:
            local_path: Path to the local DAG file.
            dag_filename: Optional custom filename in S3. Defaults to local filename.

        Returns:
            S3 key of the uploaded file.

        Raises:
            FileNotFoundError: If local_path doesn't exist.
            ValueError: If the file is not a .py file.
        """
        if not local_path.exists():
            raise FileNotFoundError(f"DAG file not found: {local_path}")

        if not local_path.suffix == ".py":
            raise ValueError(f"DAG file must be a .py file, got: {local_path}")

        filename = dag_filename or local_path.name
        s3_key = f"{self.get_package_prefix()}dags/{filename}"

        logger.info("Uploading DAG: %s -> s3://%s/%s", local_path, self.bucket, s3_key)

        with open(local_path, "rb") as f:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=f.read(),
                ContentType="text/x-python",
                Metadata={
                    "package": self.package_name,
                    "environment": self.environment,
                },
            )

        logger.info("Successfully uploaded DAG to S3")
        return s3_key

    def publish_directory(self, local_dir: Path) -> list[str]:
        """Publish all DAG files from a directory to S3.

        Args:
            local_dir: Path to directory containing DAG files.

        Returns:
            List of S3 keys for uploaded files.

        Raises:
            FileNotFoundError: If local_dir doesn't exist.
        """
        if not local_dir.exists():
            raise FileNotFoundError(f"Directory not found: {local_dir}")

        if not local_dir.is_dir():
            raise ValueError(f"Path is not a directory: {local_dir}")

        dag_files = list(local_dir.glob("*.py"))
        if not dag_files:
            logger.warning("No .py files found in %s", local_dir)
            return []

        logger.info("Found %d DAG files to upload", len(dag_files))

        uploaded_keys = []
        for dag_file in dag_files:
            s3_key = self.publish_dag_file(dag_file)
            uploaded_keys.append(s3_key)

        return uploaded_keys

    def delete_dag_file(self, dag_filename: str) -> None:
        """Delete a DAG file from S3 (within this package's prefix only).

        Args:
            dag_filename: Name of the DAG file to delete.
        """
        s3_key = f"{self.get_package_prefix()}dags/{dag_filename}"

        logger.info("Deleting DAG: s3://%s/%s", self.bucket, s3_key)
        self.s3_client.delete_object(Bucket=self.bucket, Key=s3_key)
        logger.info("Successfully deleted DAG from S3")

    def list_published_dags(self) -> list[str]:
        """List all DAGs published by this package.

        Returns:
            List of DAG filenames (without prefix).
        """
        prefix = f"{self.get_package_prefix()}dags/"
        logger.info("Listing DAGs at s3://%s/%s", self.bucket, prefix)

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
            )

            if "Contents" not in response:
                logger.info("No DAGs found")
                return []

            dags = []
            for obj in response["Contents"]:
                # Extract filename from full key
                key = obj["Key"]
                if key.endswith(".py"):
                    filename = key.split("/")[-1]
                    dags.append(filename)

            logger.info("Found %d DAGs", len(dags))
            return dags

        except ClientError as e:
            logger.error("Failed to list DAGs: %s", e)
            raise
