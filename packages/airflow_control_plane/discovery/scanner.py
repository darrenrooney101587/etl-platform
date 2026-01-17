"""Multi-package job discovery for Airflow DAG generation.

This module scans all ETL packages in the platform and discovers jobs
that export the JOB tuple convention.
"""
from __future__ import annotations

import importlib
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from etl_core.jobs import JobDefinition, discover_package_jobs

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredJob:
    """A job discovered from a package.
    
    Attributes:
        package_name: Name of the package containing the job.
        job_name: Name of the job module.
        definition: Job definition with entrypoint and description.
        module_path: Full Python module path (e.g., 'data_pipeline.jobs.example_job').
    """
    package_name: str
    job_name: str
    definition: JobDefinition
    module_path: str


class MultiPackageJobDiscovery:
    """Discovers jobs across all ETL packages in the platform."""
    
    def __init__(self, packages_root: str | None = None):
        """Initialize the multi-package job discovery.
        
        Args:
            packages_root: Path to the packages directory. If None, will attempt
                to find it relative to this module or use PYTHONPATH.
        """
        self.packages_root = packages_root or self._find_packages_root()
        self._ensure_packages_in_path()
    
    def _find_packages_root(self) -> str:
        """Find the packages root directory."""
        # First try environment variable
        if "ETL_PACKAGES_ROOT" in os.environ:
            return os.environ["ETL_PACKAGES_ROOT"]
        
        # Try to find it relative to this file
        current_file = Path(__file__).resolve()
        # Navigate up from airflow_control_plane/discovery/scanner.py
        packages_dir = current_file.parent.parent.parent
        if packages_dir.name == "packages" and packages_dir.is_dir():
            return str(packages_dir)
        
        # Fallback: look for packages in current working directory
        cwd_packages = Path.cwd() / "packages"
        if cwd_packages.is_dir():
            return str(cwd_packages)
        
        raise RuntimeError(
            "Could not find packages root directory. "
            "Set ETL_PACKAGES_ROOT environment variable or run from repository root."
        )
    
    def _ensure_packages_in_path(self) -> None:
        """Ensure the packages directory is in sys.path for imports."""
        if self.packages_root not in sys.path:
            sys.path.insert(0, self.packages_root)
    
    def _list_etl_packages(self) -> List[str]:
        """List all ETL packages (excluding etl_core and airflow_control_plane).
        
        Returns:
            List of package names that contain jobs.
        """
        packages_path = Path(self.packages_root)
        etl_packages = []
        
        for item in packages_path.iterdir():
            if not item.is_dir():
                continue
            
            # Skip special packages
            if item.name in ("etl_core", "airflow_control_plane", "__pycache__"):
                continue
            
            # Check if it has __init__.py (is a Python package)
            if not (item / "__init__.py").exists():
                continue
            
            # Check if it has a jobs subdirectory
            jobs_dir = item / "jobs"
            if jobs_dir.exists() and jobs_dir.is_dir():
                etl_packages.append(item.name)
        
        return sorted(etl_packages)
    
    def discover_all_jobs(self) -> Dict[str, List[DiscoveredJob]]:
        """Discover all jobs across all ETL packages.
        
        Returns:
            Dictionary mapping package names to lists of discovered jobs.
        """
        all_jobs: Dict[str, List[DiscoveredJob]] = {}
        
        packages = self._list_etl_packages()
        logger.info("Discovering jobs in packages: %s", packages)
        
        for package_name in packages:
            try:
                jobs_registry = discover_package_jobs(package_name)
                discovered = []
                
                for job_name, job_def in jobs_registry.items():
                    module_path = f"{package_name}.jobs.{job_name}"
                    discovered_job = DiscoveredJob(
                        package_name=package_name,
                        job_name=job_name,
                        definition=job_def,
                        module_path=module_path,
                    )
                    discovered.append(discovered_job)
                    logger.info(
                        "Discovered job: %s.%s - %s",
                        package_name,
                        job_name,
                        job_def.description,
                    )
                
                if discovered:
                    all_jobs[package_name] = discovered
            
            except Exception as e:
                logger.warning(
                    "Failed to discover jobs in package %s: %s",
                    package_name,
                    e,
                )
        
        return all_jobs
    
    def discover_all_jobs_flat(self) -> List[DiscoveredJob]:
        """Discover all jobs and return as a flat list.
        
        Returns:
            List of all discovered jobs across all packages.
        """
        all_jobs = self.discover_all_jobs()
        flat_list = []
        for jobs in all_jobs.values():
            flat_list.extend(jobs)
        return flat_list
