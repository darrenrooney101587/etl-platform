"""Unit tests for MonitoringRepository."""
import sys
import types
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from etl_core.database.client import DatabaseClient
from pipeline_processing.models.monitoring import (
    MonitoringFile,
    MonitoringFileDataProfile,
    MonitoringFileDataQuality,
    MonitoringFileRun,
    MonitoringFileSchemaDefinition,
)
from pipeline_processing.repositories.monitoring_repository import MonitoringRepository


class MonitoringRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = MagicMock(spec=DatabaseClient)
        self.repo = MonitoringRepository(self.db)

        # Mocks for ORM models
        self.MonitoringFile = MagicMock()
        self.MonitoringFileRun = MagicMock()
        self.MonitoringFileDataQuality = MagicMock()
        self.MonitoringFileDataProfile = MagicMock()
        self.MonitoringFileSchemaDefinition = MagicMock()
        self.MonitoringFileSchemaDefinitionVersion = MagicMock()

        # Inject fake etl_database_schema into sys.modules
        self._fake_mod_name = 'etl_database_schema.apps.bms_reporting.models'
        fake_mod = types.ModuleType(self._fake_mod_name)
        fake_mod.MonitoringFile = self.MonitoringFile
        fake_mod.MonitoringFileRun = self.MonitoringFileRun
        fake_mod.MonitoringFileDataQuality = self.MonitoringFileDataQuality
        fake_mod.MonitoringFileDataProfile = self.MonitoringFileDataProfile
        fake_mod.MonitoringFileSchemaDefinition = self.MonitoringFileSchemaDefinition
        fake_mod.MonitoringFileSchemaDefinitionVersion = self.MonitoringFileSchemaDefinitionVersion

        self._previous_module = sys.modules.get(self._fake_mod_name)
        sys.modules[self._fake_mod_name] = fake_mod

        # Ensure parent packages exist so imports resolve
        sys.modules.setdefault('etl_database_schema', types.ModuleType('etl_database_schema'))
        sys.modules.setdefault('etl_database_schema.apps', types.ModuleType('etl_database_schema.apps'))
        sys.modules.setdefault('etl_database_schema.apps.bms_reporting', types.ModuleType('etl_database_schema.apps.bms_reporting'))

    def tearDown(self) -> None:
        if self._previous_module:
            sys.modules[self._fake_mod_name] = self._previous_module
        else:
            sys.modules.pop(self._fake_mod_name, None)

    def test_get_monitoring_file_orm_path(self) -> None:
        # Arrange
        # Mock ORM query result
        mock_obj = MagicMock()
        mock_obj.id = 101
        mock_obj.file_name = "test_file.csv"
        mock_obj.agency_slug = "test-agency"
        mock_obj.latest_data_quality_score = 95
        mock_obj.schema_definition.id = 1
        mock_obj.schema_definition_version.id = 2
        mock_obj.is_suppressed = False
        mock_obj.s3_url = ""

        # Setup filter().order_by() chain
        # qs.filter(...).order_by(...)
        qs = self.MonitoringFile.objects.all.return_value
        qs.filter.return_value.order_by.return_value = [mock_obj]

        # Mock DB executes for agency mapping (still SQL)
        self.db.execute_query.return_value = []

        # Act
        result = self.repo.get_monitoring_file("test-agency", "test_file.csv")

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 101)
        self.assertEqual(result.file_name, "test_file.csv")
        # Ensure ORM was used
        self.assertTrue(self.MonitoringFile.objects.all.called)

    def test_create_monitoring_file_orm_path(self) -> None:
        # Arrange
        mock_obj = MagicMock()
        mock_obj.id = 202
        mock_obj.file_name = "created.csv"
        mock_obj.agency_slug = "new-agency"
        mock_obj.latest_data_quality_score = None
        mock_obj.schema_definition_id = None
        mock_obj.schema_definition_version_id = None
        mock_obj.is_suppressed = False

        self.MonitoringFile.objects.create.return_value = mock_obj

        # Act
        result = self.repo.create_monitoring_file("new-agency", "created.csv")

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 202)
        self.MonitoringFile.objects.create.assert_called_with(
            s3_url="",
            agency_slug="new-agency",
            file_name="created.csv"
        )

    def test_get_or_create_run_orm_path(self) -> None:
        # Arrange
        run_date = date(2023, 1, 1)
        run_hour = 12

        # Mock transaction.atomic context manager
        with patch("django.db.transaction.atomic"):
            # Mock select_for_update chain: .select_for_update().filter().first() -> None (create new)
            msg_qs = self.MonitoringFileRun.objects.select_for_update.return_value
            msg_qs.filter.return_value.first.return_value = None

            mock_created = MagicMock()
            mock_created.id = 303
            mock_created.monitoring_file_id = 99
            mock_created.run_date = run_date
            mock_created.run_hour = run_hour
            mock_created.agency_id = 50
            mock_created.created_at = datetime.now()
            mock_created.updated_at = datetime.now()
            mock_created.file_last_modified = None
            mock_created.file_range_lower_limit = None
            mock_created.file_size = 0

            self.MonitoringFileRun.objects.create.return_value = mock_created

            # Act
            result = self.repo.get_or_create_run(99, run_date, run_hour, agency_id=50)

            # Assert
            self.assertIsNotNone(result)
            self.assertEqual(result.id, 303)
            self.MonitoringFileRun.objects.create.assert_called()

    def test_sql_fallback_when_orm_import_fails(self) -> None:
        # Arrange - simulate import failure by removing the fake module
        sys.modules.pop(self._fake_mod_name, None)

        # Setup DB mock for SQL path
        self.db.execute_query.return_value = [
            {
                "id": 999,
                "file_name": "sql.csv",
                "agency_slug": "sql-agency",
                "latest_data_quality_score": None,
                "schema_definition_id": None,
                "schema_definition_version_id": None,
                "s3_url": None,
                "is_suppressed": False
            }
        ]

        # Act
        result = self.repo.get_monitoring_file("sql-agency", "sql.csv")

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 999)
        # Should have called execute_query, not ORM
        self.assertTrue(self.db.execute_query.called)


if __name__ == "__main__":
    unittest.main()
