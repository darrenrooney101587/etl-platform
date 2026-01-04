"""CLI entrypoint for the file_processing module.

Dispatches subcommands (currently `data-quality`) to the appropriate job entrypoints.
"""
from __future__ import annotations

import sys
from typing import List

from file_processing.jobs.data_quality_job import entrypoint as data_quality_entrypoint


def main(argv: List[str] | None = None) -> int:
    """Minimal CLI main that prints help and exits 0.

    Args:
        argv: List of command line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code integer (0 on success).
    """
    if argv is None:
        argv = sys.argv[1:]

    # If user asked for help or provided no args, print a short help message
    if not argv or "-h" in argv or "--help" in argv:
        print("file-processing: available commands")
        print("  data-quality --agency-id <id>   Run attachment data quality checks")
        return 0

    if argv[0] == "data-quality":
        return data_quality_entrypoint(argv[1:])

    print("file-processing: unknown command. Use --help for options.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
