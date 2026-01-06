"""Shared job discovery helpers used by package CLIs.

This module provides a small, well-tested routine to discover job modules
for any package (for example `data_pipeline`, `file_processing`, `observability`).
Job modules must expose a top-level `JOB` variable with the shape
`(entrypoint, description)`.
"""
from typing import Callable, Dict, List, NamedTuple
import importlib
import pkgutil
import logging

logger = logging.getLogger(__name__)


class JobDefinition(NamedTuple):
    entrypoint: Callable[[List[str]], int]
    description: str


def discover_package_jobs(package_name: str) -> Dict[str, JobDefinition]:
    """Discover job modules under the given package's `jobs` subpackage.

    Args:
        package_name: Top-level package name (e.g. 'data_pipeline').

    Returns:
        Mapping of job name -> JobDefinition.
    """
    entries: Dict[str, JobDefinition] = {}
    full_pkg = f"{package_name}.jobs"
    try:
        jobs_pkg = importlib.import_module(full_pkg)
    except Exception:
        logger.debug("No %s package available for discovery", full_pkg, exc_info=True)
        return entries

    for finder, name, ispkg in pkgutil.iter_modules(jobs_pkg.__path__):
        if name.startswith("_") or name == "registry":
            continue
        mod_name = f"{full_pkg}.{name}"
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            logger.warning("Failed to import job module %s", mod_name, exc_info=True)
            continue

        if hasattr(mod, "JOB"):
            candidate = getattr(mod, "JOB")
            if isinstance(candidate, JobDefinition):
                entries[name] = candidate
            elif isinstance(candidate, (list, tuple)) and len(candidate) == 2 and callable(candidate[0]) and isinstance(candidate[1], str):
                entries[name] = JobDefinition(entrypoint=candidate[0], description=candidate[1])
            else:
                logger.warning("JOB in %s is not a JobDefinition or tuple(entrypoint, description); ignoring", mod_name)
        else:
            logger.debug("Job module %s does not expose JOB; ignoring", mod_name)

    return entries
