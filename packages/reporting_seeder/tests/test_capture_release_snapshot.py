import unittest
from unittest.mock import MagicMock, patch
import os

from reporting_seeder.jobs.capture_release_snapshot import entrypoint


class CaptureReleaseSnapshotJobTests(unittest.TestCase):
    def setUp(self):
        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            "DJANGO_SETTINGS_MODULE": "reporting_seeder.settings",
            "DB_HOST": "localhost",
            "DB_PASSWORD": "fake",
            "SEEDER_REFRESH_CONCURRENTLY": "true",
        })
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    @patch("reporting_seeder.jobs.capture_release_snapshot.ReleaseSnapshotProcessor")
    @patch("reporting_seeder.jobs.capture_release_snapshot.ReleaseSnapshotRepository")
    @patch("reporting_seeder.jobs.capture_release_snapshot.MaterializedViewRepository")
    @patch("reporting_seeder.jobs.capture_release_snapshot.ManifestRepository")
    @patch("reporting_seeder.jobs.capture_release_snapshot.DatabaseClient")
    @patch("reporting_seeder.jobs.capture_release_snapshot.bootstrap_django")
    def test_capture_snapshot_success(
        self,
        mock_bootstrap,
        mock_db_client_cls,
        mock_manifest_repo_cls,
        mock_mv_repo_cls,
        mock_snapshot_repo_cls,
        mock_processor_cls
    ):
        # Setup mocks
        mock_manifest_repo = mock_manifest_repo_cls.return_value
        mock_mv_repo = mock_mv_repo_cls.return_value
        mock_processor = mock_processor_cls.return_value

        # Mock manifest return
        mock_manifest_repo.get_manifest_by_table.return_value = {
            "id": 1,
            "table_name": "reporting.test_view",
            "query": "SELECT 1"
        }

        # Run entrypoint
        argv = [
            "--table-name", "reporting.test_view",
            "--release-tag", "v123",
            "--release-version", "1.0.0"
        ]
        exit_code = entrypoint(argv)

        # Asserts
        self.assertEqual(exit_code, 0)
        mock_bootstrap.assert_called_once()
        mock_manifest_repo.get_manifest_by_table.assert_called_with("reporting.test_view")
        mock_mv_repo.refresh_view.assert_called_with("reporting.test_view", concurrently=True)
        mock_mv_repo.analyze_view.assert_called_with("reporting.test_view")

        # Verify processor call
        mock_processor.capture_snapshot.assert_called_once()
        call_kwargs = mock_processor.capture_snapshot.call_args[1]
        self.assertEqual(call_kwargs["manifest"]["table_name"], "reporting.test_view")
        self.assertEqual(call_kwargs["release_tag"], "v123")
        self.assertEqual(call_kwargs["release_version"], "1.0.0")

    @patch("reporting_seeder.jobs.capture_release_snapshot.ManifestRepository")
    @patch("reporting_seeder.jobs.capture_release_snapshot.DatabaseClient")
    @patch("reporting_seeder.jobs.capture_release_snapshot.bootstrap_django")
    def test_missing_manifest_returns_error(
        self,
        mock_bootstrap,
        mock_db_client,
        mock_manifest_repo_cls
    ):
        mock_manifest_repo = mock_manifest_repo_cls.return_value
        mock_manifest_repo.get_manifest_by_table.return_value = None

        argv = ["--table-name", "missing.view", "--release-tag", "v1"]
        exit_code = entrypoint(argv)

        self.assertEqual(exit_code, 1)

if __name__ == "__main__":
    unittest.main()
