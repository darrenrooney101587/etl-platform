"""CLI entrypoint for reporting_seeder jobs.

This module tries to import the shared CLI helper using the development layout
(`packages.etl_core.cli`) and falls back to the top-level package
(`etl_core.cli`) so it works both when running from the repo root and when the
package is installed in a venv/container.
"""
from __future__ import annotations


from etl_core.cli import main_for_package



def main() -> None:
    """Invoke the shared package CLI dispatcher for reporting_seeder."""
    raise SystemExit(main_for_package("reporting-seeder", "reporting_seeder"))


if __name__ == "__main__":
    main()
