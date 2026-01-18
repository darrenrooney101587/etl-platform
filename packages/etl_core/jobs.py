"""Job discovery and definition utilities for ETL packages.

This module provides utilities for discovering and managing job definitions
across ETL packages. Jobs are discovered by scanning for modules that export
a JOB tuple in the format: (entrypoint_function, description_string).
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class JobDefinition:
    """Definition of a discovered job.

    Attributes:
        entrypoint: Callable that accepts argv and returns an exit code.
        description: Human-readable description of the job.
    """
    entrypoint: Callable[[List[str]], int]
    description: str


def discover_package_jobs(package_name: str) -> Dict[str, JobDefinition]:
    """Discover all jobs in a package by scanning for JOB tuples.

    Scans the `<package_name>.jobs` subpackage for modules that export a JOB
    tuple in the format: (entrypoint_callable, description_string).

    Args:
        package_name: Top-level package name to scan (e.g., 'pipeline_processing').

    Returns:
        Dictionary mapping job names to JobDefinition instances.

    Example:
        >>> registry = discover_package_jobs('pipeline_processing')
        >>> job = registry.get('example_job')
        >>> if job:
        ...     exit_code = job.entrypoint(['--help'])
    """
    registry: Dict[str, JobDefinition] = {}
    jobs_package_name = f"{package_name}.jobs"

    try:
        jobs_package = importlib.import_module(jobs_package_name)
    except ImportError:
        logger.debug("No jobs package found for %s", package_name)
        return registry

    # Iterate over all modules in the jobs package
    for module_info in pkgutil.iter_modules(jobs_package.__path__):
        # Handle both tuple format (finder, name, ispkg) and ModuleInfo object
        # for backwards compatibility with different Python versions/environments
        if isinstance(module_info, tuple):
            _, module_name, is_pkg = module_info
        else:
            module_name = module_info.name
            is_pkg = module_info.ispkg

        if is_pkg:
            continue

        full_module_name = f"{jobs_package_name}.{module_name}"

        try:
            module = importlib.import_module(full_module_name)

            # Check if module exports a JOB tuple
            if hasattr(module, "JOB"):
                job_tuple = getattr(module, "JOB")

                # Validate JOB tuple format
                if not isinstance(job_tuple, tuple) or len(job_tuple) != 2:
                    logger.warning(
                        "Module %s exports JOB but it's not a 2-tuple (entrypoint, description)",
                        full_module_name
                    )
                    continue

                entrypoint, description = job_tuple

                if not callable(entrypoint):
                    logger.warning(
                        "Module %s JOB tuple has non-callable entrypoint",
                        full_module_name
                    )
                    continue

                if not isinstance(description, str):
                    logger.warning(
                        "Module %s JOB tuple has non-string description",
                        full_module_name
                    )
                    continue

                registry[module_name] = JobDefinition(
                    entrypoint=entrypoint,
                    description=description
                )
                logger.debug("Discovered job: %s (%s)", module_name, description)

        except Exception as e:
            logger.warning(
                "Failed to import or process module %s: %s",
                full_module_name,
                e
            )

    return registry
