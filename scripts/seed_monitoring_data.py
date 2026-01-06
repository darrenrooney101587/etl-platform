"""Lightweight DB seeder for monitoring tables — Django-free.

This script mirrors the behavior of the Django `seed_monitoring_data` command you
attached. It does not depend on Django and can be run directly from this repo.

Features added to improve reproducibility and developer experience:
- Accept an explicit --env-file to load package-level environment variables.
- Accept --random-seed to make generated data deterministic for reproducible runs.
- Improved error messages when DB credentials are missing or connection fails.
- More informative prints about what was created.

Behavior:
- Load package-level .env (packages/file_processing/.env) to pick up DB credentials
  unless an explicit --env-file is provided.
- Optionally accept an existing monitoring_file id; otherwise create (or reuse)
  a monitoring_file for the given agency_slug and file_name.
- Create sample schema definitions (if missing) and assign a schema to the file
  when appropriate.
- Insert a few monitoring_file_run rows and matching data_quality and data_profile rows.
- Update monitoring_file.latest_data_quality_score to match the most recent run.

Usage examples:
  python scripts/seed_monitoring_data.py --agency-slug demo-agency --file-name demo-file --runs 5
  python scripts/seed_monitoring_data.py --monitoring-file-id 17390 --runs 3
  python scripts/seed_monitoring_data.py --env-file packages/file_processing/.env --random-seed 42
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from etl_core.database.client import DatabaseClient

logger = logging.getLogger(__name__)


def _execute_sql_file(db: DatabaseClient, file_path: Path) -> None:
    """Read and execute SQL statements from a file."""
    if not file_path.exists():
        logger.warning("SQL stub file not found: %s", file_path)
        return

    logger.info("Executing SQL stub: %s", file_path)
    with file_path.open("r", encoding="utf8") as f:
        sql_content = f.read()

    # Split by semicolon to handle multiple statements if present, though usually these are single inserts
    statements = [s.strip() for s in sql_content.split(";") if s.strip()]

    for sql in statements:
        try:
            # We use the raw cursor execution for these inserts to handle them exactly as written
            db.execute_query(sql, [])
        except Exception as e:
            # Log but continue (e.g. if record already exists)
            logger.warning("Failed to execute statement in %s: %s", file_path.name, e)


def seed_from_stubs(db: DatabaseClient, stub_dir: Path) -> None:
    """Seed database using SQL stub files in dependency order."""
    # Check if main record exists to avoid re-seeding if already done
    try:
        rows = db.execute_query("SELECT id FROM reporting.monitoring_file WHERE id = 1", [])
        if rows:
            logger.info("Monitoring file with ID=1 already exists. Assuming stubs are seeded.")
            return
    except Exception as e:
        logger.warning("Could not check for existing monitoring_file (id=1): %s", e)

    # Order matters due to foreign keys
    files = [
        "monitoring_file.sql",
        "monitoring_file_run.sql",
        "monitoring_file_result.sql",
        "monitoring_file_failed_validation.sql",
    ]

    for fname in files:
        _execute_sql_file(db, stub_dir / fname)


def _load_dotenv_file(path: Path, overwrite: bool = False) -> None:
    """Load simple KEY=VALUE pairs from a dotenv file into os.environ.

    This intentionally does not add a dependency on python-dotenv; it is a
    minimal loader adequate for local development .env files used by this repo.

    Args:
        path: Path to the .env file.
        overwrite: If True, overwrite existing environment variables.
    """
    if not path.exists():
        return
    with path.open("r", encoding="utf8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            if overwrite or key not in os.environ:
                os.environ[key] = val


def _load_package_envs(preferred_package: str = "file_processing", env_file: Optional[str] = None) -> None:
    """Load environment variables from well-known package-level .env locations.

    Loading order (first found will be loaded, but existing OS env vars are not
    overwritten):
      1. Explicit --env-file (if provided)
      2. packages/<preferred_package>/.env
      3. packages/etl_core/.env
      4. repo root .env

    Args:
        preferred_package: Package to prefer for the .env file (default: file_processing).
        env_file: Optional explicit .env path (absolute or relative to repo root).
    """
    repo_root = Path(__file__).resolve().parents[1]

    candidates = []
    if env_file:
        candidates.append(Path(env_file).expanduser())
    candidates.extend(
        [
            repo_root / "packages" / preferred_package / ".env",
            repo_root / "packages" / "etl_core" / ".env",
            repo_root / ".env",
        ]
    )
    for p in candidates:
        _load_dotenv_file(p, overwrite=False)


def _ensure_schema_definition(db: DatabaseClient, name: str, definition: Dict[str, Any], description: Optional[str] = None) -> int:
    """Ensure a schema definition exists and return its id."""
    rows = db.execute_query("SELECT id FROM reporting.monitoring_file_schema_definition WHERE name = %s", [name])
    if rows:
        return rows[0]["id"]

    rows = db.execute_query(
        "INSERT INTO reporting.monitoring_file_schema_definition (name, description, definition, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW()) RETURNING id",
        [name, description or "", json.dumps(definition)],
    )
    return rows[0]["id"]


def _get_monitoring_file_by_id(db: DatabaseClient, mf_id: int) -> Optional[Dict[str, Any]]:
    """Return the monitoring_file row for a given id, or None if not found."""
    rows = db.execute_query("SELECT id, file_name, agency_slug, schema_definition_id, latest_data_quality_score FROM reporting.monitoring_file WHERE id = %s", [mf_id])
    return rows[0] if rows else None


def _get_or_create_monitoring_file(db: DatabaseClient, agency_slug: str, file_name: str, schema_definition_id: Optional[int] = None, s3_url: Optional[str] = None) -> int:
    """Get an existing monitoring_file by agency and file_name or create it and return id."""
    rows = db.execute_query("SELECT id, schema_definition_id FROM reporting.monitoring_file WHERE agency_slug = %s AND file_name = %s", [agency_slug, file_name])
    if rows:
        existing = rows[0]
        # if schema provided and not set on file, update it
        if schema_definition_id and not existing.get("schema_definition_id"):
            db.execute_query("UPDATE reporting.monitoring_file SET schema_definition_id = %s, updated_at = NOW() WHERE id = %s", [schema_definition_id, existing["id"]])
        return existing["id"]

    rows = db.execute_query(
        "INSERT INTO reporting.monitoring_file (agency_slug, file_name, schema_definition_id, s3_url, created_at, updated_at) VALUES (%s, %s, %s, %s, NOW(), NOW()) RETURNING id",
        [agency_slug, file_name, schema_definition_id, s3_url or ""],
    )
    return rows[0]["id"]


def _create_run(db: DatabaseClient, monitoring_file_id: int, run_date: date, run_hour: int, file_size: int = 0, file_last_modified: Optional[datetime] = None) -> int:
    """Insert a monitoring_file_run row and return its id."""
    rows = db.execute_query(
        "INSERT INTO reporting.monitoring_file_run (monitoring_file_id, run_date, run_hour, agency_id, file_last_modified, file_size, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW()) RETURNING id",
        [monitoring_file_id, run_date, run_hour, None, file_last_modified, file_size],
    )
    return rows[0]["id"]


def _upsert_quality_and_profile(db: DatabaseClient, run_id: int, score: int, passed: bool, metrics: Dict[str, Any], deductions: Dict[str, Any]) -> None:
    """Insert or update the data quality and profile rows for a given run."""
    db.execute_query(
        "INSERT INTO reporting.monitoring_file_data_quality (monitoring_file_run_id, score, passed, metrics, deductions, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, NOW(), NOW()) ON CONFLICT (monitoring_file_run_id) DO UPDATE SET score = EXCLUDED.score, passed = EXCLUDED.passed, metrics = EXCLUDED.metrics, deductions = EXCLUDED.deductions, updated_at = NOW()",
        [run_id, score, passed, json.dumps(metrics), json.dumps(deductions)],
    )
    db.execute_query(
        "INSERT INTO reporting.monitoring_file_data_profile (monitoring_file_run_id, profile_payload, created_at, updated_at) VALUES (%s, %s, NOW(), NOW()) ON CONFLICT (monitoring_file_run_id) DO UPDATE SET profile_payload = EXCLUDED.profile_payload, updated_at = NOW()",
        [run_id, json.dumps({"summary": "seeded"})],
    )


def _update_monitoring_file_latest_score(db: DatabaseClient, monitoring_file_id: int, score: int) -> None:
    """Update the monitoring_file.latest_data_quality_score field."""
    db.execute_query("UPDATE reporting.monitoring_file SET latest_data_quality_score = %s, updated_at = NOW() WHERE id = %s", [score, monitoring_file_id])


def _assign_schema_by_filename(db: DatabaseClient, monitoring_file_id: int, file_name: str) -> Optional[int]:
    """Assign a schema to the monitoring_file using filename heuristics and return schema id if available."""
    lower = file_name.lower()
    schema_name = None
    if 'officer' in lower or 'personnel' in lower:
        schema_name = 'officer_detail'
    elif 'incident' in lower or 'report' in lower:
        schema_name = 'incident_report'
    elif 'training' in lower:
        schema_name = 'training_records'
    elif 'payroll' in lower or 'pay' in lower:
        schema_name = 'payroll_export'
    elif 'equipment' in lower or 'inventory' in lower:
        schema_name = 'equipment_inventory'
    else:
        schema_name = 'officer_detail'

    # look up schema id
    rows = db.execute_query("SELECT id FROM reporting.monitoring_file_schema_definition WHERE name = %s", [schema_name])
    if not rows:
        return None
    schema_id = rows[0]["id"]
    # Update the monitoring_file if not set
    db.execute_query("UPDATE reporting.monitoring_file SET schema_definition_id = %s, updated_at = NOW() WHERE id = %s AND (schema_definition_id IS NULL OR schema_definition_id = '')", [schema_id, monitoring_file_id])
    return schema_id


def main(argv: Optional[list] = None) -> int:
    """CLI entrypoint.

    Args:
        argv: Optional argument list to parse (defaults to sys.argv).

    Returns:
        Exit code (0 on success, non-zero on failure).
    """
    parser = argparse.ArgumentParser()
    # attempt to auto-detect the package name from the current working directory
    repo_root = Path(__file__).resolve().parents[1]
    default_package = "file_processing"
    try:
        cwd_parts = Path.cwd().resolve().parts
        if "packages" in cwd_parts:
            idx = cwd_parts.index("packages")
            if idx + 1 < len(cwd_parts):
                default_package = cwd_parts[idx + 1]
    except Exception:
        # fall back to the explicit default if any error occurs
        default_package = "file_processing"

    parser.add_argument("--agency-slug", required=False)
    parser.add_argument("--file-name", required=False)
    parser.add_argument("--monitoring-file-id", type=int, required=False)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--start-date", required=False, help="YYYY-MM-DD")
    parser.add_argument("--run-hour", type=int, required=False, help="Specific hour for the run (0-23). If not set, random hours are used.")
    parser.add_argument("--bare-run", action="store_true", help="Create the run record only; do not insert fake quality/profile data.")
    parser.add_argument("--schema", required=False, help="schema name to ensure exists and optionally assign")
    parser.add_argument("--env-file", required=False, help="Path to a .env file to load before connecting to the DB")
    parser.add_argument("--package", required=False, default=default_package, help=f"Package name whose packages/<name>/.env should be loaded (default: {default_package})")
    parser.add_argument("--dry-run", action="store_true", help="If set, do not connect to DB; print the actions that would be performed.")
    parser.add_argument("--random-seed", type=int, required=False, help="If provided, uses this seed for deterministic output")
    parser.add_argument("--use-stubs", action="store_true", help="Seed from SQL stubs in data/stub instead of generating random data")
    parser.add_argument("--stub-dir", required=False, help="Directory containing SQL stubs (default: data/stub)")
    args = parser.parse_args(argv)

    # Load environment variables with optional explicit env file
    # prefer package-level .env for the package being exercised (e.g. packages/file_processing/.env)
    _load_package_envs(preferred_package=args.package, env_file=args.env_file)

    # If dry-run requested, simulate the seeding actions without touching the DB
    if args.dry_run:
        # deterministic behavior when random-seed is provided
        if args.random_seed is not None:
            random.seed(args.random_seed)
            logger.info("Dry-run using deterministic random seed=%s", args.random_seed)

        agency = args.agency_slug or "demo-agency"
        fname = args.file_name or "demo-file"
        runs = args.runs
        if args.start_date:
            start = date.fromisoformat(args.start_date)
        else:
            start = date.today() - timedelta(days=runs)

        print(f"DRY RUN: package={args.package} agency={agency} file={fname} runs={runs} start={start}")
        for i in range(runs):
            run_date = start + timedelta(days=i)
            run_hour = random.randint(0, 23)
            file_size = random.randint(1000, 1000000)
            score = random.randint(60, 100)
            passed = score >= 80
            metrics = {"rows": random.randint(1000, 5000)}
            deductions = {"seeded": 100 - score}
            print(f"DRY RUN -> would create run date={run_date} hour={run_hour} file_size={file_size} score={score} passed={passed} metrics={metrics} deductions={deductions}")
        return 0

    # If deterministic reproducibility is desired, set the random seed
    if args.random_seed is not None:
        random.seed(args.random_seed)
        logger.info("Using deterministic random seed=%s", args.random_seed)

    # Initialize database client and provide helpful guidance if connection fails
    try:
        db = DatabaseClient()
        # quick smoke-test query to fail fast with a clear message if DB creds are missing
        try:
            db.execute_query("SELECT 1", [])
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.error(
                "Database connection failed: %s\nPlease ensure DB_HOST, DB_PORT, DB_NAME, DB_USER, and DB_PASSWORD are set in the environment or .env file (e.g., packages/file_processing/.env).",
                exc,
            )
            raise
    except Exception as e:  # pragma: no cover - environment dependent
        print(f"CRITICAL ERROR: Failed to initialize database client: {e}")
        return 2

    if args.use_stubs:
        # Determine stub directory
        if args.stub_dir:
            stub_dir = Path(args.stub_dir)
        else:
            # Default to repo_root/data/stub
            stub_dir = repo_root / "data" / "stub"

        logger.info("Seeding from stubs in: %s", stub_dir)
        seed_from_stubs(db, stub_dir)
        print("Seeding from stubs completed.")
        return 0

    # Ensure schema definitions if requested
    if args.schema:
        # small sample def
        sample_def = {"columns": [{"name": "id", "type": "integer"}, {"name": "name", "type": "string"}]}
        schema_id = _ensure_schema_definition(db, args.schema, sample_def)
        logger.info("Ensured schema definition %s -> id=%s", args.schema, schema_id)

    mf_id: Optional[int] = None
    if args.monitoring_file_id:
        mf = _get_monitoring_file_by_id(db, args.monitoring_file_id)
        if not mf:
            raise SystemExit(f"monitoring_file id {args.monitoring_file_id} not found")
        mf_id = mf["id"]
    else:
        # If no inputs provided, default to demo values for quick local development.
        if not args.agency_slug or not args.file_name:
            logger.info("No agency/file provided — defaulting to demo-agency/demo-file for quick seed")
            args.agency_slug = args.agency_slug or "demo-agency"
            args.file_name = args.file_name or "demo-file"
        mf_id = _get_or_create_monitoring_file(db, args.agency_slug, args.file_name, None, None)

    print("Using monitoring_file id:", mf_id)
    print(f"DEBUG: mf_id={mf_id} type={type(mf_id)}")
    sys.stdout.flush()
    if mf_id is None:
        print("CRITICAL: mf_id is None!")
        return 1

    # assign schema by filename if available
    _assign_schema_by_filename(db, mf_id, args.file_name or "")

    if args.start_date:
        start = date.fromisoformat(args.start_date)
    else:
        start = date.today() - timedelta(days=args.runs)

    last_created_run_id = None
    last_score = None

    for i in range(args.runs):
        run_date = start + timedelta(days=i)
        if args.run_hour is not None:
            run_hour = args.run_hour
        else:
            run_hour = random.randint(0, 23)

        file_size = random.randint(1000, 1000000)
        run_id = _create_run(db, mf_id, run_date, run_hour, file_size)

        if args.bare_run:
            print(f"created bare run id={run_id} date={run_date} hour={run_hour} (no quality/profile data)")
        else:
            # generate quality sample
            score = random.randint(60, 100)
            passed = score >= 80
            metrics = {"rows": random.randint(1000, 5000)}
            deductions = {"seeded": 100 - score}

            _upsert_quality_and_profile(db, run_id, score, passed, metrics, deductions)

            last_created_run_id = run_id
            last_score = score

            print(f"created run id={run_id} date={run_date} hour={run_hour} score={score}")

    if last_score is not None:
        _update_monitoring_file_latest_score(db, mf_id, last_score)
        print(f"updated monitoring_file {mf_id} latest_data_quality_score={last_score}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
