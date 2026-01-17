"""Tests for DAG publisher."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from airflow_dag_publisher.publisher import DAGPublisher


class TestDAGPublisher(unittest.TestCase):
    """Test DAGPublisher class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_s3_client = MagicMock()
        self.publisher = DAGPublisher(
            bucket="test-bucket",
            environment="dev",
            package_name="test_package",
            s3_client=self.mock_s3_client,
        )

    def test_init_validates_environment(self):
        """Test that invalid environments are rejected."""
        with self.assertRaises(ValueError) as cm:
            DAGPublisher(
                bucket="test-bucket",
                environment="invalid",
                package_name="test_package",
            )
        self.assertIn("environment must be one of", str(cm.exception))

    def test_init_validates_package_name(self):
        """Test that invalid package names are rejected."""
        with self.assertRaises(ValueError) as cm:
            DAGPublisher(
                bucket="test-bucket",
                environment="dev",
                package_name="test package!",  # Invalid: spaces and special chars
            )
        self.assertIn("must be alphanumeric", str(cm.exception))

    def test_get_package_prefix(self):
        """Test package prefix generation."""
        prefix = self.publisher.get_package_prefix()
        self.assertEqual(prefix, "dev/test_package/")

    def test_verify_bucket_exists_success(self):
        """Test successful bucket verification."""
        self.mock_s3_client.head_bucket.return_value = {}
        result = self.publisher.verify_bucket_exists()
        self.assertTrue(result)
        self.mock_s3_client.head_bucket.assert_called_once_with(Bucket="test-bucket")

    def test_verify_bucket_exists_not_found(self):
        """Test bucket verification when bucket doesn't exist."""
        from botocore.exceptions import ClientError

        error = ClientError(
            {"Error": {"Code": "404"}},
            "head_bucket",
        )
        self.mock_s3_client.head_bucket.side_effect = error
        result = self.publisher.verify_bucket_exists()
        self.assertFalse(result)

    def test_publish_dag_file_validates_extension(self):
        """Test that non-.py files are rejected."""
        with self.assertRaises(ValueError) as cm:
            self.publisher.publish_dag_file(Path("/tmp/test.txt"))
        self.assertIn("must be a .py file", str(cm.exception))

    def test_list_published_dags_empty(self):
        """Test listing DAGs when none exist."""
        self.mock_s3_client.list_objects_v2.return_value = {}
        dags = self.publisher.list_published_dags()
        self.assertEqual(dags, [])

    def test_list_published_dags_with_results(self):
        """Test listing DAGs with results."""
        self.mock_s3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "dev/test_package/dags/dag1.py"},
                {"Key": "dev/test_package/dags/dag2.py"},
                {"Key": "dev/test_package/dags/metadata.json"},  # Should be filtered
            ]
        }
        dags = self.publisher.list_published_dags()
        self.assertEqual(sorted(dags), ["dag1.py", "dag2.py"])


if __name__ == "__main__":
    unittest.main()
