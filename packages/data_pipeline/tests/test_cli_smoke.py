from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["poetry", "run", "data-pipeline", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_list_jobs_smoke() -> None:
    result = _run_command(["list"])
    assert result.returncode == 0
    assert "healthcheck" in result.stdout


def test_run_healthcheck_smoke() -> None:
    result = _run_command(["run", "healthcheck"])
    assert result.returncode == 0


def test_help_healthcheck_smoke() -> None:
    result = _run_command(["help", "healthcheck"])
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()


def test_unknown_job_smoke() -> None:
    result = _run_command(["run", "does-not-exist"])
    assert result.returncode != 0
    combined_output = f"{result.stdout}\n{result.stderr}"
    assert "healthcheck" in combined_output
