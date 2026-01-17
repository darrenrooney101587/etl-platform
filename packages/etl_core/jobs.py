"""Job discovery helpers used by package CLIs.

This module provides a small helper to find job modules under a package's
`jobs` subpackage. Each job module must export a top-level `JOB` tuple:

    JOB = (entrypoint, "description")

Where `entrypoint` is a callable that accepts (argv: List[str]) -> int.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List


@dataclass
class JobDefinition:
    entrypoint: Callable[[List[str]], int]
    description: str


def discover_package_jobs(package_name: str) -> Dict[str, JobDefinition]:
    """Discover job modules under the `<package_name>.jobs` package.

    Returns a mapping module_name -> JobDefinition. Modules that fail to
    import are skipped.
    """
    registry: Dict[str, JobDefinition] = {}
    jobs_pkg_name = f"{package_name}.jobs"

    try:
        pkg = importlib.import_module(jobs_pkg_name)
    except Exception:
        return registry

    if not getattr(pkg, "__path__", None):
        return registry

    for finder, mod_name, ispkg in pkgutil.iter_modules(pkg.__path__):
        full_name = f"{jobs_pkg_name}.{mod_name}"
        try:
            module = importlib.import_module(full_name)
        except Exception:
            continue
        if hasattr(module, "JOB"):
            job_val = getattr(module, "JOB")
            if isinstance(job_val, tuple) and len(job_val) >= 2 and callable(job_val[0]):
                entrypoint = job_val[0]
                description = str(job_val[1])
                registry[mod_name] = JobDefinition(entrypoint=entrypoint, description=description)
    return registry


def run_job_from_registry(registry: Dict[str, JobDefinition], name: str, argv: Iterable[str]) -> int:
    job = registry.get(name)
    if job is None:
        available = ", ".join(sorted(registry.keys()))
        raise RuntimeError(f"Unknown job '{name}'. Available: {available}")
    return job.entrypoint(list(argv))
