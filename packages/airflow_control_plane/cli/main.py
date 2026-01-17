"""CLI entrypoint for the Airflow control plane.

This CLI provides commands for:
- Discovering jobs across all ETL packages
- Generating Airflow DAG files from discovered jobs
- Synchronizing DAGs when new jobs are added
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from airflow_control_plane.discovery.scanner import MultiPackageJobDiscovery
from airflow_control_plane.dag_generator.generator import DagGenerator

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def cmd_discover(args: argparse.Namespace) -> int:
    """Discover all jobs across ETL packages.
    
    Args:
        args: Parsed command-line arguments.
    
    Returns:
        Exit code (0 for success).
    """
    setup_logging(args.verbose)
    
    packages_root = args.packages_root or os.environ.get("ETL_PACKAGES_ROOT")
    discovery = MultiPackageJobDiscovery(packages_root)
    
    all_jobs = discovery.discover_all_jobs()
    
    if not all_jobs:
        print("No jobs discovered.")
        return 0
    
    print(f"\nDiscovered jobs in {len(all_jobs)} package(s):\n")
    
    for package_name, jobs in sorted(all_jobs.items()):
        print(f"📦 {package_name}")
        for job in jobs:
            print(f"  └─ {job.job_name}: {job.definition.description}")
        print()
    
    total = sum(len(jobs) for jobs in all_jobs.values())
    print(f"Total: {total} job(s)")
    
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate Airflow DAG files from discovered jobs.
    
    Args:
        args: Parsed command-line arguments.
    
    Returns:
        Exit code (0 for success).
    """
    setup_logging(args.verbose)
    
    packages_root = args.packages_root or os.environ.get("ETL_PACKAGES_ROOT")
    dags_dir = args.dags_dir or os.environ.get("AIRFLOW_DAGS_DIR", "./dags")
    
    logger.info("Discovering jobs from packages: %s", packages_root or "default")
    discovery = MultiPackageJobDiscovery(packages_root)
    jobs = discovery.discover_all_jobs_flat()
    
    if not jobs:
        logger.warning("No jobs discovered. No DAGs generated.")
        return 0
    
    logger.info("Found %d job(s). Generating DAGs...", len(jobs))
    
    generator = DagGenerator(dags_dir)
    generated_files = generator.generate_all_dags(jobs)
    
    if args.clean:
        logger.info("Cleaning stale DAG files...")
        generator.clean_stale_dags(jobs)
    
    print(f"\n✓ Successfully generated {len(generated_files)} DAG file(s) in {dags_dir}")
    
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """Synchronize DAGs by discovering jobs and generating DAG files.
    
    This is a convenience command that combines discover and generate.
    
    Args:
        args: Parsed command-line arguments.
    
    Returns:
        Exit code (0 for success).
    """
    setup_logging(args.verbose)
    
    packages_root = args.packages_root or os.environ.get("ETL_PACKAGES_ROOT")
    dags_dir = args.dags_dir or os.environ.get("AIRFLOW_DAGS_DIR", "./dags")
    
    logger.info("Synchronizing Airflow DAGs...")
    logger.info("  Packages root: %s", packages_root or "default")
    logger.info("  DAGs directory: %s", dags_dir)
    
    # Discover jobs
    discovery = MultiPackageJobDiscovery(packages_root)
    jobs = discovery.discover_all_jobs_flat()
    
    if not jobs:
        logger.warning("No jobs discovered.")
        return 0
    
    logger.info("Discovered %d job(s)", len(jobs))
    
    # Generate DAGs
    generator = DagGenerator(dags_dir)
    generated_files = generator.generate_all_dags(jobs)
    
    # Clean stale DAGs
    generator.clean_stale_dags(jobs)
    
    print(f"\n✓ Synchronized {len(generated_files)} DAG(s)")
    print(f"  DAGs directory: {dags_dir}")
    
    return 0


def main() -> int:
    """Main CLI entrypoint.
    
    Returns:
        Exit code.
    """
    parser = argparse.ArgumentParser(
        prog="airflow-control-plane",
        description="Airflow control plane for automatic DAG generation",
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Discover command
    discover_parser = subparsers.add_parser(
        "discover",
        help="Discover all jobs across ETL packages",
    )
    discover_parser.add_argument(
        "--packages-root",
        help="Path to packages directory (default: auto-detect or $ETL_PACKAGES_ROOT)",
    )
    discover_parser.set_defaults(func=cmd_discover)
    
    # Generate command
    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate Airflow DAG files from discovered jobs",
    )
    generate_parser.add_argument(
        "--packages-root",
        help="Path to packages directory (default: auto-detect or $ETL_PACKAGES_ROOT)",
    )
    generate_parser.add_argument(
        "--dags-dir",
        help="Output directory for generated DAG files (default: ./dags or $AIRFLOW_DAGS_DIR)",
    )
    generate_parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove stale DAG files for jobs that no longer exist",
    )
    generate_parser.set_defaults(func=cmd_generate)
    
    # Sync command
    sync_parser = subparsers.add_parser(
        "sync",
        help="Synchronize DAGs (discover + generate + clean)",
    )
    sync_parser.add_argument(
        "--packages-root",
        help="Path to packages directory (default: auto-detect or $ETL_PACKAGES_ROOT)",
    )
    sync_parser.add_argument(
        "--dags-dir",
        help="Output directory for generated DAG files (default: ./dags or $AIRFLOW_DAGS_DIR)",
    )
    sync_parser.set_defaults(func=cmd_sync)
    
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
