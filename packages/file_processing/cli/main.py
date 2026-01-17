"""CLI entrypoint for file_processing jobs.

This module invokes the shared CLI helper from etl_core to discover and run
jobs defined in file_processing.jobs.
"""
from __future__ import annotations

from etl_core.cli import main_for_package


def main() -> None:
    """Invoke the shared package CLI dispatcher for file_processing."""
    raise SystemExit(main_for_package("file-processing", "file_processing"))


if __name__ == "__main__":
    main()
