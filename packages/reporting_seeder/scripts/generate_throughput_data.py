"""Small helper to populate many test manifests for throughput testing.

This script attempts to use a DATABASE_URL env var or DB_* env vars. It also
accepts an explicit --database-url DSN. If credentials are not available it
exits early with a helpful message instead of trying to connect and raising a
psycopg2 OperationalError.
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Optional

from etl_core.database.client import DatabaseClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _has_db_credentials() -> bool:
    """Return True if we have enough config to build a DB connection.

    We accept either:
      - DATABASE_URL environment variable, or
      - DB_USER and DB_PASSWORD environment variables (DB_HOST/DB_NAME optional)
    """
    if os.getenv("DATABASE_URL"):
        return True
    if os.getenv("DB_USER") and os.getenv("DB_PASSWORD"):
        return True
    return False


def generate_data(count: int = 500, database_url: Optional[str] = None) -> None:
    """Insert `count` custom manifest rows for throughput testing.

    Args:
        count: number of manifests to create
        database_url: optional DSN to pass to DatabaseClient (takes precedence over env)
    """
    if not database_url and not _has_db_credentials():
        logger.error(
            "No DB credentials found. Set DATABASE_URL or DB_USER and DB_PASSWORD in your environment, or pass --database-url."
        )
        raise SystemExit(2)

    client = DatabaseClient(dsn=database_url) if database_url else DatabaseClient()

    logger.info("Connecting to database...")

    # Clean up old test data
    logger.info("Cleaning up old throughput test data...")
    # Use a parameterized LIKE to avoid raw '%' characters being interpreted by psycopg2's pyformat
    try:
        client.execute_query(
            "DELETE FROM reporting.seeder_custom_report_manifest WHERE table_name LIKE %s",
            ["reporting.throughput_test_%"],
        )
    except Exception:
        logger.exception(
            "Failed to execute cleanup DELETE. SQL=%s params=%s",
            "DELETE FROM reporting.seeder_custom_report_manifest WHERE table_name LIKE %s",
            ["reporting.throughput_test_%"],
        )
        raise

    # Insert records
    logger.info("Generating %s custom report manifests...", count)

    start_id = 10000

    for i in range(count):
        curr_id = start_id + i
        table_name = f"reporting.throughput_test_{i}"
        report_name = f"Throughput Test {i}"
        query = f"SELECT {i} AS id, md5(random()::text) AS val, NOW() as created_at"

        sql = """
        INSERT INTO reporting.seeder_custom_report_manifest
        (id, table_name, report_name, agency_id, agency_slug, query, database_id, enabled)
        VALUES (%s, %s, %s, 1, 'test-agency', %s, 1, TRUE)
        ON CONFLICT (id) DO UPDATE SET 
            table_name = EXCLUDED.table_name,
            query = EXCLUDED.query,
            enabled = TRUE;
        """

        try:
            client.execute_query(sql, [curr_id, table_name, report_name, query])
        except Exception:
            logger.exception("Failed to execute INSERT. SQL=%s params=%s", sql, [curr_id, table_name, report_name, query])
            raise

        if (i + 1) % 50 == 0:
            logger.info("Inserted %s records...", i + 1)

    logger.info("Successfully inserted %s records.", count)
    logger.info("You can now run the refresh_all job to test throughput.")
    logger.info(
        "Recommended: poetry run python -m packages.reporting_seeder.cli.main refresh_all"
    )
    logger.info(
        "Alternate (if running file directly): PYTHONPATH=. poetry run python packages/reporting_seeder/cli/main.py refresh_all"
    )


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate throughput test data for reporting_seeder")
    p.add_argument("--count", type=int, default=500, help="Number of reports to generate")
    p.add_argument(
        "--database-url",
        dest="database_url",
        help="Optional full DATABASE_URL (overrides env vars)",
    )
    return p


# Try to load a local .env file (packages/reporting_seeder/.env) to make the script
# usable in local dev without manually exporting env vars. This mirrors the pattern
# used by the package integration tests: they attempt to import python-dotenv but
# don't require it.
try:
    from dotenv import load_dotenv  # type: ignore

    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info("Loaded environment from %s", env_path)
except Exception:
    # dotenv isn't required; fall back to reading the real environment
    pass

if __name__ == "__main__":
    parser = _build_argparser()
    args = parser.parse_args()

    try:
        generate_data(args.count, args.database_url)
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - runtime DB errors depend on environment
        logger.exception("Failed to generate throughput data: %s", exc)
        raise
