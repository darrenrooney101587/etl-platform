"""Utility to create a monitoring_file and monitoring_file_run for local testing.

This is a convenience script for local development only. It uses the repository
helpers to create a monitoring_file (if missing) and a run so the data quality
job can be exercised end-to-end.

Usage:
    python scripts/create_test_run.py --agency-slug demo-agency --file-name demo-file --run-date 2026-01-04 --run-hour 12

Note: This is NOT intended for production use. Upstream job orchestration is
responsible for creating monitoring_file and monitoring_file_run records.
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from etl_core.database.client import DatabaseClient
from file_processing.repositories.monitoring_repository import MonitoringRepository

logger = logging.getLogger(__name__)


def _load_dotenv_file(path: Path, overwrite: bool = False) -> None:
    """Load simple KEY=VALUE pairs from a .env file into os.environ.

    This is intentionally small and dependency-free (no python-dotenv). Lines
    beginning with # are ignored. Quoted values have surrounding quotes stripped.
    Existing environment variables are preserved unless `overwrite` is True.
    """
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                # strip surrounding single/double quotes
                if (val.startswith("\"") and val.endswith("\"")) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                if overwrite or key not in os.environ:
                    os.environ[key] = val
    except Exception as exc:
        logger.warning("Failed to load .env from %s: %s", path, exc)


def _load_package_envs(preferred_package: str = "file_processing") -> None:
    """Look for package-level .env files and load them (non-destructively).

    Search order (first match wins for a given key):
      - packages/<preferred_package>/.env
      - packages/etl_core/.env
      - .env (repo root)
    """
    repo_root = Path(__file__).resolve().parents[1]
    candidates = [
        repo_root / "packages" / preferred_package / ".env",
        repo_root / "packages" / "etl_core" / ".env",
        repo_root / ".env",
    ]
    for p in candidates:
        _load_dotenv_file(p, overwrite=False)
        if p.exists():
            logger.debug("Loaded .env from %s", p)


def _masked(name: str) -> str:
    v = os.getenv(name)
    if not v:
        return "<unset>"
    if len(v) <= 4:
        return "****"
    return v[:2] + "*" * (len(v) - 4) + v[-2:]


def _validate_db_envs() -> None:
    """Fail fast with a helpful message if there is no usable DB configuration.

    Acceptable configurations:
      - DATABASE_URL is set, or
      - DB_HOST, DB_NAME, DB_USER and DB_PASSWORD are all set.

    If neither is true, exit with a helpful message.
    """
    if os.getenv("DATABASE_URL"):
        return
    required = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        msg = (
            "Missing DB configuration: the following environment variables are not set: "
            + ", ".join(missing)
            + ". Please set them in your environment or .env file."
        )
        logger.error(msg)
        raise RuntimeError(msg)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Create monitoring file and run for local testing")
    parser.add_argument("--agency-slug", required=True)
    parser.add_argument("--file-name", required=True)
    parser.add_argument("--run-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--run-hour", type=int, required=True)
    parser.add_argument("--s3-url", required=False, help="Optional s3://... url to store on monitoring_file")

    args = parser.parse_args(argv)

    # Load package-level .env files so local development can configure DB/S3
    _load_package_envs(preferred_package="file_processing")

    # Log a few DB settings for debugging (do not log secrets)
    logger.info("DB settings: host=%s db=%s user=%s", _masked("DB_HOST"), _masked("DB_NAME"), _masked("DB_USER"))

    # Validate DB environment variables
    _validate_db_envs()

    try:
        db = DatabaseClient()
        repo = MonitoringRepository(db)

        mf = repo.get_monitoring_file(args.agency_slug, args.file_name)
    except Exception as exc:  # pragma: no cover - runtime environment errors
        logger.error("Failed to connect to the database or execute query: %s", exc)
        logger.info("Current DB settings: host=%s port=%s db=%s user=%s", os.getenv("DB_HOST"), os.getenv("DB_PORT"), os.getenv("DB_NAME"), os.getenv("DB_USER"))
        logger.error("Tip: Ensure your package-level .env (packages/file_processing/.env) or environment variables point to a reachable Postgres instance. For local runs inside Docker use DB_HOST=host.docker.internal; for local Postgres use DB_HOST=localhost and ensure Postgres is running.")
        raise

    if mf is None:
        print(f"Creating monitoring_file for {args.agency_slug}/{args.file_name}")
        mf = repo.create_monitoring_file(args.agency_slug, args.file_name, s3_url=args.s3_url)
    else:
        print(f"Found monitoring_file id={mf.id}")

    # Ensure we have a valid id for the monitoring_file. If the INSERT/SELECT
    # unexpectedly returned a row without an id, abort with a helpful message.
    if mf is None or getattr(mf, "id", None) is None:
        logger.error(
            "MonitoringFile lookup/creation did not return a valid id. This prevents run creation.\n"
            "Check your reporting.monitoring_file table for the inserted row and ensure the DB user has INSERT/SELECT/RETURNING privileges."
        )
        raise RuntimeError("MonitoringFile missing id after create/lookup; aborting")

    run_date = datetime.strptime(args.run_date, "%Y-%m-%d").date()
    run = repo.get_run(mf.id, run_date, args.run_hour)
    if run is None:
        print(f"Creating run for monitoring_file_id={mf.id} date={run_date} hour={args.run_hour}")
        run = repo.get_or_create_run(mf.id, run_date, args.run_hour)
    else:
        print(f"Found run id={run.id}")

    print("Done. MonitoringFile id=", mf.id, "run id=", run.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
