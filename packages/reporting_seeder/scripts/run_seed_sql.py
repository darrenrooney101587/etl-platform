"""Small helper to apply the reporting_seeder SQL seed file using DatabaseClient.

This script uses `etl_core.support.db_factory.get_database_client` so callers
can configure DJANGO_DB_CLIENT_PATH to use a Django-backed client if desired.
"""
from __future__ import annotations

import os
from pathlib import Path

from etl_core.support.db_factory import get_database_client


def main() -> int:
    pkg_root = Path(__file__).resolve().parents[1]
    sql_path = pkg_root / "data" / "seed_reporting_seeder.sql"
    if not sql_path.exists():
        print("Seed SQL not found:", sql_path)
        return 1

    with sql_path.open("r", encoding="utf-8") as fh:
        sql = fh.read()

    db = get_database_client()
    print("Applying seed SQL to:", os.getenv("DB_HOST", "localhost"))
    try:
        # Split statements by semicolon conservatively — the seed uses simple statements.
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            print("Executing:", stmt.splitlines()[0][:120])
            db.execute_query(stmt)
    except Exception as exc:
        print("Failed to apply seed SQL:", exc)
        return 2
    finally:
        try:
            db.close()
        except Exception:
            pass

    print("Seed applied successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
