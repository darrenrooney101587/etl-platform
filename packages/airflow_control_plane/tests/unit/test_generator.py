"""Unit tests for DAG generator."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from etl_core.jobs import JobDefinition
from airflow_control_plane.discovery.scanner import DiscoveredJob
from airflow_control_plane.dag_generator.generator import DagGenerator


class TestDagGenerator(unittest.TestCase):
    """Tests for DagGenerator."""
    
    def test_generate_dag_for_job(self):
        """Test DAG generation for a single job."""
        mock_entrypoint = lambda argv: 0
        job_def = JobDefinition(entrypoint=mock_entrypoint, description="Test job")
        
        job = DiscoveredJob(
            package_name="test_pkg",
            job_name="test_job",
            definition=job_def,
            module_path="test_pkg.jobs.test_job",
        )
        
        with TemporaryDirectory() as tmpdir:
            generator = DagGenerator(tmpdir)
            dag_code = generator.generate_dag_for_job(job)
            
            # Verify key elements in generated code
            self.assertIn("dag_id='test_pkg_test_job'", dag_code)
            self.assertIn("from test_pkg.jobs.test_job import JOB", dag_code)
            self.assertIn("description='Test job'", dag_code)
            self.assertIn("tags=['test_pkg', 'etl', 'auto-generated']", dag_code)
    
    def test_write_dag_file(self):
        """Test writing DAG file to disk."""
        mock_entrypoint = lambda argv: 0
        job_def = JobDefinition(entrypoint=mock_entrypoint, description="Test")
        
        job = DiscoveredJob(
            package_name="pkg",
            job_name="job",
            definition=job_def,
            module_path="pkg.jobs.job",
        )
        
        with TemporaryDirectory() as tmpdir:
            generator = DagGenerator(tmpdir)
            dag_code = "# test dag code"
            filepath = generator.write_dag_file(job, dag_code)
            
            self.assertTrue(filepath.exists())
            self.assertEqual(filepath.name, "pkg_job_dag.py")
            
            with open(filepath, 'r') as f:
                content = f.read()
            self.assertEqual(content, dag_code)
    
    def test_generate_all_dags(self):
        """Test generating DAGs for multiple jobs."""
        mock_entrypoint = lambda argv: 0
        
        jobs = [
            DiscoveredJob(
                package_name="pkg1",
                job_name="job1",
                definition=JobDefinition(entrypoint=mock_entrypoint, description="Job 1"),
                module_path="pkg1.jobs.job1",
            ),
            DiscoveredJob(
                package_name="pkg2",
                job_name="job2",
                definition=JobDefinition(entrypoint=mock_entrypoint, description="Job 2"),
                module_path="pkg2.jobs.job2",
            ),
        ]
        
        with TemporaryDirectory() as tmpdir:
            generator = DagGenerator(tmpdir)
            generated_files = generator.generate_all_dags(jobs)
            
            self.assertEqual(len(generated_files), 2)
            
            filenames = [f.name for f in generated_files]
            self.assertIn("pkg1_job1_dag.py", filenames)
            self.assertIn("pkg2_job2_dag.py", filenames)
    
    def test_clean_stale_dags(self):
        """Test cleaning of stale DAG files."""
        mock_entrypoint = lambda argv: 0
        
        current_jobs = [
            DiscoveredJob(
                package_name="pkg",
                job_name="current_job",
                definition=JobDefinition(entrypoint=mock_entrypoint, description="Current"),
                module_path="pkg.jobs.current_job",
            ),
        ]
        
        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create a stale DAG file
            stale_file = tmpdir_path / "pkg_old_job_dag.py"
            stale_file.write_text("# old dag")
            
            # Create a current DAG file
            current_file = tmpdir_path / "pkg_current_job_dag.py"
            current_file.write_text("# current dag")
            
            generator = DagGenerator(tmpdir)
            generator.clean_stale_dags(current_jobs)
            
            # Stale file should be removed
            self.assertFalse(stale_file.exists())
            
            # Current file should remain
            self.assertTrue(current_file.exists())


if __name__ == "__main__":
    unittest.main()
