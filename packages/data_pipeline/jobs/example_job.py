"""Example job for `data_pipeline` demonstrating the JOB convention.

This job is intentionally minimal and side-effect free so you can run it
locally as a demo. It shows how to expose a `JOB` tuple that the shared
`etl_core` discovery and CLI helpers can find and run.
"""
from __future__ import annotations

import argparse
from typing import List


def entrypoint(argv: List[str]) -> int:
    """Simple entrypoint that prints a greeting multiple times.

    Args:
        argv: CLI arguments (usually sys.argv[1:]).

    Returns:
        Exit code (0 success, non-zero failure).
    """
    parser = argparse.ArgumentParser(prog="data-pipeline example_job")
    parser.add_argument("--name", default="world", help="Name to greet")
    parser.add_argument("--repeat", type=int, default=1, help="Number of times to print the greeting")
    args = parser.parse_args(argv)

    for i in range(args.repeat):
        print(f"[example_job] Hello, {args.name}! ({i+1}/{args.repeat})")

    return 0


# Expose the job using the required JOB tuple convention
JOB = (entrypoint, "Example job: prints a greeting")
