from __future__ import annotations

import subprocess
from pathlib import Path


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        ["poetry", "run", "data-pipeline", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def test_healthcheck_smoke() -> None:
    result = _run_command(["healthcheck"])
    assert result.returncode == 0
    assert result.stdout.strip() == "healthcheck: ok"


def test_run_transform_smoke() -> None:
    result = _run_command(["run-transform", "--feed", "arrests"])
    assert result.returncode == 0
    assert result.stdout.strip() == "run-transform: would process feed 'arrests'"


def test_ingest_smoke() -> None:
    result = _run_command(["ingest", "--source", "api"])
    assert result.returncode == 0
    assert result.stdout.strip() == "ingest: would ingest source 'api'"


def test_missing_required_arg() -> None:
    result = _run_command(["run-transform"])
    assert result.returncode != 0
    assert "usage:" in result.stderr
