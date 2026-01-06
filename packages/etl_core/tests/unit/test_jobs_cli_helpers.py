import sys
import unittest
from types import ModuleType
from unittest.mock import patch, MagicMock

from packages.etl_core.jobs import discover_package_jobs, JobDefinition
from packages.etl_core.cli import make_job_cli, run_job_by_name


class TestJobsDiscoveryAndCliHelpers(unittest.TestCase):
    def test_discover_package_jobs_finds_job_tuple(self):
        # Simulate a package 'fake_pkg.jobs' with a single module 'job1'
        fake_jobs_pkg = ModuleType("fake_pkg.jobs")
        # pkgutil.iter_modules expects a package __path__ attribute
        fake_jobs_pkg.__path__ = ["/nonexistent/path"]

        fake_module = ModuleType("fake_pkg.jobs.job1")

        def fake_entrypoint(argv):
            return 42

        fake_module.JOB = (fake_entrypoint, "desc")

        # Patch importlib.import_module to return our fake modules
        def import_module_side_effect(name, package=None):
            if name == "fake_pkg.jobs":
                return fake_jobs_pkg
            if name == "fake_pkg.jobs.job1":
                return fake_module
            raise ImportError(name)

        # Patch pkgutil.iter_modules to yield a single module 'job1'
        fake_iter = [(None, "job1", False)]

        with patch("pkgutil.iter_modules", return_value=fake_iter):
            with patch("importlib.import_module", side_effect=import_module_side_effect):
                registry = discover_package_jobs("fake_pkg")

        self.assertIn("job1", registry)
        jd = registry["job1"]
        self.assertIsInstance(jd, JobDefinition)
        self.assertEqual(jd.description, "desc")
        self.assertTrue(callable(jd.entrypoint))
        self.assertEqual(jd.entrypoint([]), 42)

    def test_run_job_by_name_unknown(self):
        parser = make_job_cli("test-prog")
        registry = {}
        # Unknown job should return exit code 1 and print available (empty)
        code = run_job_by_name(registry, "nope", [])
        self.assertEqual(code, 1)

    def test_run_job_by_name_invokes_entrypoint(self):
        def ep(argv):
            return 7

        registry = {"j": JobDefinition(entrypoint=ep, description="d")}
        code = run_job_by_name(registry, "j", ["--help"])
        self.assertEqual(code, 7)


if __name__ == "__main__":
    unittest.main()
