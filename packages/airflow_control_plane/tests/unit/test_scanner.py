"""Unit tests for job discovery scanner."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from etl_core.jobs import JobDefinition
from airflow_control_plane.discovery.scanner import (
    DiscoveredJob,
    MultiPackageJobDiscovery,
)


class TestMultiPackageJobDiscovery(unittest.TestCase):
    """Tests for MultiPackageJobDiscovery."""
    
    def test_discovered_job_dataclass(self):
        """Test DiscoveredJob dataclass creation."""
        mock_entrypoint = lambda argv: 0
        job_def = JobDefinition(entrypoint=mock_entrypoint, description="test job")
        
        discovered = DiscoveredJob(
            package_name="test_pkg",
            job_name="test_job",
            definition=job_def,
            module_path="test_pkg.jobs.test_job",
        )
        
        self.assertEqual(discovered.package_name, "test_pkg")
        self.assertEqual(discovered.job_name, "test_job")
        self.assertEqual(discovered.definition, job_def)
        self.assertEqual(discovered.module_path, "test_pkg.jobs.test_job")
    
    @patch("airflow_control_plane.discovery.scanner.Path")
    def test_list_etl_packages(self, mock_path):
        """Test listing of ETL packages."""
        # Create mock directory structure
        mock_packages_dir = MagicMock()
        mock_path.return_value = mock_packages_dir
        
        # Mock package directories
        pkg1 = MagicMock()
        pkg1.is_dir.return_value = True
        pkg1.name = "data_pipeline"
        pkg1.__truediv__ = lambda self, other: MagicMock(exists=lambda: True, is_dir=lambda: True)
        
        pkg2 = MagicMock()
        pkg2.is_dir.return_value = True
        pkg2.name = "file_processing"
        pkg2.__truediv__ = lambda self, other: MagicMock(exists=lambda: True, is_dir=lambda: True)
        
        # Mock etl_core (should be skipped)
        etl_core = MagicMock()
        etl_core.is_dir.return_value = True
        etl_core.name = "etl_core"
        
        mock_packages_dir.iterdir.return_value = [pkg1, pkg2, etl_core]
        
        discovery = MultiPackageJobDiscovery("/fake/path")
        packages = discovery._list_etl_packages()
        
        # etl_core should be excluded
        self.assertIn("data_pipeline", packages)
        self.assertIn("file_processing", packages)
        self.assertNotIn("etl_core", packages)
    
    @patch("airflow_control_plane.discovery.scanner.discover_package_jobs")
    @patch.object(MultiPackageJobDiscovery, "_list_etl_packages")
    def test_discover_all_jobs(self, mock_list_packages, mock_discover):
        """Test discovery of all jobs across packages."""
        mock_list_packages.return_value = ["test_pkg"]
        
        # Mock discovered jobs
        mock_entrypoint = lambda argv: 0
        mock_discover.return_value = {
            "job1": JobDefinition(entrypoint=mock_entrypoint, description="Job 1"),
            "job2": JobDefinition(entrypoint=mock_entrypoint, description="Job 2"),
        }
        
        discovery = MultiPackageJobDiscovery("/fake/path")
        all_jobs = discovery.discover_all_jobs()
        
        self.assertIn("test_pkg", all_jobs)
        self.assertEqual(len(all_jobs["test_pkg"]), 2)
        
        job_names = [j.job_name for j in all_jobs["test_pkg"]]
        self.assertIn("job1", job_names)
        self.assertIn("job2", job_names)
    
    @patch("airflow_control_plane.discovery.scanner.discover_package_jobs")
    @patch.object(MultiPackageJobDiscovery, "_list_etl_packages")
    def test_discover_all_jobs_flat(self, mock_list_packages, mock_discover):
        """Test flat list discovery."""
        mock_list_packages.return_value = ["pkg1", "pkg2"]
        
        mock_entrypoint = lambda argv: 0
        
        def mock_discover_side_effect(pkg_name):
            if pkg_name == "pkg1":
                return {"job1": JobDefinition(entrypoint=mock_entrypoint, description="J1")}
            elif pkg_name == "pkg2":
                return {"job2": JobDefinition(entrypoint=mock_entrypoint, description="J2")}
            return {}
        
        mock_discover.side_effect = mock_discover_side_effect
        
        discovery = MultiPackageJobDiscovery("/fake/path")
        jobs = discovery.discover_all_jobs_flat()
        
        self.assertEqual(len(jobs), 2)
        job_names = [j.job_name for j in jobs]
        self.assertIn("job1", job_names)
        self.assertIn("job2", job_names)


if __name__ == "__main__":
    unittest.main()
