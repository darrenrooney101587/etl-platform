import unittest
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestCliSmoke(unittest.TestCase):
    def _run_command(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["poetry", "run", "data-pipeline", *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_list_jobs_smoke(self) -> None:
        result = self._run_command(["list"])
        self.assertEqual(result.returncode, 0, f"Command failed with stderr: {result.stderr}")
        self.assertIn("healthcheck", result.stdout)

    def test_run_healthcheck_smoke(self) -> None:
        result = self._run_command(["run", "healthcheck"])
        self.assertEqual(result.returncode, 0, f"Command failed with stderr: {result.stderr}")

    def test_help_healthcheck_smoke(self) -> None:
        result = self._run_command(["help", "healthcheck"])
        self.assertEqual(result.returncode, 0, f"Command failed with stderr: {result.stderr}")
        self.assertIn("usage:", result.stdout.lower())

    def test_unknown_job_smoke(self) -> None:
        result = self._run_command(["run", "does-not-exist"])
        self.assertNotEqual(result.returncode, 0)
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertIn("healthcheck", combined_output)


if __name__ == "__main__":
    unittest.main()
