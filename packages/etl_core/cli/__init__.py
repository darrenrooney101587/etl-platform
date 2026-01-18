"""Shared CLI builder helpers for package job CLIs.

This module provides a minimal builder for the `list`/`run`/`help` style
CLI used by package job CLIs.
"""
from __future__ import annotations

import argparse
import sys
from typing import Callable, Dict, Iterable, List

from ..jobs import JobDefinition, discover_package_jobs

import importlib.util
import os
import logging

logger = logging.getLogger(__name__)


def _load_package_env(package_name: str) -> None:
    """Load a package-level .env file into os.environ if present.

    Behavior:
    - Looks for a `.env` file in the package directory (first location in
      spec.submodule_search_locations).
    - Loads KEY=VALUE lines, ignores comments and blank lines.
    - Does not overwrite existing environment variables (only sets missing keys).
    """
    try:
        spec = importlib.util.find_spec(package_name)
        if not spec or not spec.submodule_search_locations:
            return
        pkg_dir = list(spec.submodule_search_locations)[0]
        env_path = os.path.join(pkg_dir, ".env")
        if not os.path.exists(env_path):
            return

        logger.info("Loading package .env from %s", env_path)
        with open(env_path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        logger.debug("Failed to load package .env for %s", package_name, exc_info=True)


def make_job_cli(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List available jobs")

    run_parser = subparsers.add_parser("run", help="Run a named job")
    run_parser.add_argument("job_name", help="Job to run")
    run_parser.add_argument("job_args", nargs=argparse.REMAINDER)

    help_parser = subparsers.add_parser("help", help="Show job-specific help")
    help_parser.add_argument("job_name", help="Job to show help for")

    return parser


def run_job_by_name(registry: Dict[str, JobDefinition], name: str, argv: Iterable[str]) -> int:
    job = registry.get(name)
    if job is None:
        available = ", ".join(sorted(registry.keys()))
        print(f"Unknown job '{name}'. Available jobs: {available}", file=sys.stderr)
        return 1
    return job.entrypoint(list(argv))


def main_for_package(prog: str, package_name: str) -> int:
    """Canonical CLI entrypoint for a package that exposes jobs.

    Args:
        prog: Program name used in the argparse help (e.g. 'data-pipeline').
        package_name: Top-level package to discover jobs for (e.g. 'data_pipeline').

    Returns:
        Exit code integer.
    """
    # Load per-package .env (if present) so local development can set
    # package-scoped environment like LOCAL_S3_ROOT without global changes.
    _load_package_env(package_name)

    # Ensure basic logging is configured for package-level CLI runs when no
    # handlers are present. This guarantees that jobs invoked via
    # `main_for_package(...)->run` will emit INFO logs to stdout by default
    # (matching the behavior when running the job module directly).
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    parser = make_job_cli(prog)
    args = parser.parse_args()

    registry = discover_package_jobs(package_name)

    if args.command == "list":
        for name in sorted(registry.keys()):
            print(name)
        return 0

    if args.command == "run":
        job_args = args.job_args
        if job_args and job_args[0] == "--":
            job_args = job_args[1:]
        return run_job_by_name(registry, args.job_name, job_args)

    if args.command == "help":
        return run_job_by_name(registry, args.job_name, ["--help"])

    parser.print_usage()
    return 2
