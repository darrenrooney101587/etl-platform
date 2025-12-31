"""
Unit tests for the DatabaseClient in data_pipeline.database.client.

These tests focus on database query functionality and data processing utilities
exposed by the DatabaseClient methods, using injected mock connections for isolation.
"""

import sys
from unittest.mock import MagicMock
from tests.unit.conftest import setup_mocks

setup_mocks()

import os
import unittest
from unittest.mock import MagicMock, Mock

from data_pipeline.database.client import DatabaseClient


class TestDatabaseClient(unittest.TestCase):
    """Test cases for DatabaseClient methods.

    Each test method injects a mock Django connections mapping to avoid real DB access.
    """

    def _make_client_with_cursor(self) -> tuple[DatabaseClient, MagicMock, Mock]:
        """Helper to create a client with a prepared mock connection/cursor.

        :returns: Tuple of (client, mock_connections, mock_cursor)
        :rtype: tuple[DatabaseClient, MagicMock, Mock]
        """
        mock_connections: MagicMock = MagicMock()
        mock_connection: Mock = Mock()
        mock_connections.__getitem__.return_value = mock_connection

        mock_cursor: Mock = Mock()
        mock_connection.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_connection.cursor.return_value.__exit__ = Mock(return_value=None)

        client = DatabaseClient(connections=mock_connections)
        return client, mock_connections, mock_cursor

    def test_get_attachment_files_for_s3_processing_success(self) -> None:
        """Test successful retrieval of attachment files."""
        client, _mock_conns, mock_cursor = self._make_client_with_cursor()

        # Mock cursor description (column names)
        mock_cursor.description = [
            ("filename",), ("original_filename",), ("attachable_type",),
            ("mime_type",), ("byte_size",), ("benchmark_user_id",),
            ("relation_id",), ("output_filename",),
        ]

        # Mock result data
        mock_cursor.fetchall.return_value = [
            (
                "file1.pdf", "original1.pdf", "Form", "application/pdf",
                1024, 101, "F001", "F001_file1.pdf",
            ),
            (
                "file2.jpg", "original2.jpg", "UserDocument", "image/jpeg",
                2048, 102, "E002", "E002_John_Doe_original2.jpg",
            ),
        ]

        result = client.get_attachment_files_for_s3_processing(123)

        # Verify query execution
        mock_cursor.execute.assert_called_once()
        self.assertEqual(mock_cursor.execute.call_args[0][1], [123])

        # Verify result structure
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["filename"], "file1.pdf")
        self.assertEqual(result[0]["attachable_type"], "Form")
        self.assertEqual(result[1]["filename"], "file2.jpg")
        self.assertEqual(result[1]["attachable_type"], "UserDocument")

    def test_get_attachment_files_for_s3_processing_empty_result(self) -> None:
        """Test attachment files retrieval with empty result."""
        client, _mock_conns, mock_cursor = self._make_client_with_cursor()

        mock_cursor.description = [("filename",)]
        mock_cursor.fetchall.return_value = []

        result = client.get_attachment_files_for_s3_processing(123)

        self.assertEqual(result, [])
        mock_cursor.execute.assert_called_once()

    def test_get_attachment_files_for_s3_processing_exception(self) -> None:
        """Test attachment files retrieval with database exception."""
        client, _mock_conns, mock_cursor = self._make_client_with_cursor()

        mock_cursor.execute.side_effect = Exception("Database connection error")

        with self.assertRaisesRegex(Exception, "Database connection error"):
            client.get_attachment_files_for_s3_processing(123)

    def test_get_agency_s3_slug_success(self) -> None:
        """Test successful S3 slug retrieval."""
        client, _mock_conns, mock_cursor = self._make_client_with_cursor()

        mock_cursor.fetchone.return_value = ("test-agency-slug",)

        result = client.get_agency_s3_slug(123)

        self.assertEqual(result, "test-agency-slug")
        mock_cursor.execute.assert_called_once()

        # Verify the SQL query and parameters
        call_args = mock_cursor.execute.call_args
        sql_query = call_args[0][0]
        params = call_args[0][1]

        # SQL should reference the reporting table and use a %s placeholder for the agency id
        self.assertIsInstance(sql_query, str)
        self.assertIn("FROM reporting.ref_agency_designations", sql_query)
        self.assertIn("%s", sql_query)
        # Parameters should include the agency id
        self.assertEqual(params, [123])

    def test_get_agency_s3_slug_not_found(self) -> None:
        """Test S3 slug retrieval when agency not found."""
        client, _mock_conns, mock_cursor = self._make_client_with_cursor()

        mock_cursor.fetchone.return_value = None

        result = client.get_agency_s3_slug(123)

        self.assertEqual(result, "")
        mock_cursor.execute.assert_called_once()

    def test_get_agency_s3_slug_exception(self) -> None:
        """Test S3 slug retrieval with database exception."""
        client, _mock_conns, mock_cursor = self._make_client_with_cursor()

        mock_cursor.execute.side_effect = Exception("Database error")

        with self.assertRaisesRegex(Exception, "Database error"):
            client.get_agency_s3_slug(123)

    def test_get_organization_employment_history_success(self) -> None:
        """Test successful employment history retrieval."""
        client, _mock_conns, mock_cursor = self._make_client_with_cursor()

        # Mock cursor description (column names)
        mock_cursor.description = [
            ("display_name",), ("employee_id",), ("effective_date",),
            ("employment_action",), ("title_rank",), ("employment_type",),
            ("comment",), ("status",), ("supervisor",), ("tour_of_duty",), ("role",),
        ]

        # Mock result data
        mock_cursor.fetchall.return_value = [
            (
                "IT Department",
                "E001",
                "2023-01-01",
                "HIRE",
                "Senior Developer",
                "Full-time",
                "Initial hire",
                "Active",
                "John Manager",
                "8x5",
                "Developer",
            ),
            (
                "HR Department",
                "E002",
                "2023-02-01",
                "PROMOTION",
                "HR Manager",
                "Full-time",
                "Promoted to manager",
                "Active",
                "Jane Director",
                "8x5",
                "Manager",
            ),
        ]

        result = client.get_organization_employment_history(123)

        # Verify query execution
        mock_cursor.execute.assert_called_once()
        self.assertEqual(mock_cursor.execute.call_args[0][1], [123])

        # Verify result structure
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["display_name"], "IT Department")
        self.assertEqual(result[0]["employee_id"], "E001")
        self.assertEqual(result[0]["employment_action"], "HIRE")
        self.assertEqual(result[1]["display_name"], "HR Department")
        self.assertEqual(result[1]["employee_id"], "E002")
        self.assertEqual(result[1]["employment_action"], "PROMOTION")

    def test_get_organization_employment_history_empty_result(self) -> None:
        """Test employment history retrieval with empty result."""
        client, _mock_conns, mock_cursor = self._make_client_with_cursor()

        mock_cursor.description = [("display_name",)]
        mock_cursor.fetchall.return_value = []

        result = client.get_organization_employment_history(123)

        self.assertEqual(result, [])
        mock_cursor.execute.assert_called_once()

    def test_get_organization_employment_history_exception(self) -> None:
        """Test employment history retrieval with database exception."""
        client, _mock_conns, mock_cursor = self._make_client_with_cursor()

        mock_cursor.execute.side_effect = Exception("Query execution failed")

        with self.assertRaisesRegex(Exception, "Query execution failed"):
            client.get_organization_employment_history(123)

    def test_cursor_context_manager_usage(self) -> None:
        """Test that all methods use cursor context manager properly."""
        client, mock_conns, mock_cursor = self._make_client_with_cursor()

        # Prepare to simulate three different calls
        mock_cursor.description = [("test",)]
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = None

        # Call each function
        client.get_attachment_files_for_s3_processing(123)
        client.get_agency_s3_slug(123)
        client.get_organization_employment_history(123)

        # All functions should have called the context manager methods
        mock_connection = mock_conns.__getitem__.return_value
        self.assertEqual(mock_connection.cursor.return_value.__enter__.call_count, 3)
        self.assertEqual(mock_connection.cursor.return_value.__exit__.call_count, 3)

    def test_sql_injection_protection(self) -> None:
        """Test that methods use parameterized queries for SQL injection protection."""
        client, _mock_conns, mock_cursor = self._make_client_with_cursor()

        mock_cursor.description = [("test",)]
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = None

        agency_id = 123

        # Test each function
        client.get_attachment_files_for_s3_processing(agency_id)
        client.get_agency_s3_slug(agency_id)
        client.get_organization_employment_history(agency_id)

        # Verify all execute calls use parameterized queries
        for call in mock_cursor.execute.call_args_list:
            # Each call should have SQL string and parameters list
            self.assertEqual(len(call[0]), 2)
            sql_query, params = call[0]
            self.assertIsInstance(sql_query, str)
            self.assertIsInstance(params, list)
            self.assertIn(agency_id, params)
            # Verify query uses %s placeholders, not string formatting
            self.assertIn("%s", sql_query)
            self.assertNotIn(str(agency_id), sql_query)

    def test_column_mapping_accuracy(self) -> None:
        """Test that column mapping from cursor description works correctly."""
        client, _mock_conns, mock_cursor = self._make_client_with_cursor()

        # Test with specific column order
        mock_cursor.description = [("col1",), ("col2",), ("col3",)]
        mock_cursor.fetchall.return_value = [("val1", "val2", "val3")]

        result = client.get_attachment_files_for_s3_processing(123)

        # Verify column mapping is correct
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["col1"], "val1")
        self.assertEqual(result[0]["col2"], "val2")
        self.assertEqual(result[0]["col3"], "val3")


if __name__ == "__main__":
    unittest.main()
