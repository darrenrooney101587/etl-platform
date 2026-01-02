from typing import Callable, Dict, List, NamedTuple
import importlib
import pkgutil
import logging

logger = logging.getLogger(__name__)

class JobDefinition(NamedTuple):
    entrypoint: Callable[[List[str]], int]
    description: str

def _load_static_cli_entries() -> Dict[str, JobDefinition]:
    """Load explicit CLI-backed jobs for backward compatibility.

    These are jobs that live under `data_pipeline.cli` (legacy layout) and are
    kept for compatibility with existing console scripts.
    """
    entries: Dict[str, JobDefinition] = {}
    try:
        mod = importlib.import_module("data_pipeline.cli.get_s3_files")
        if hasattr(mod, "main"):
            entries["get-s3-files"] = JobDefinition(entrypoint=mod.main, description="Process S3 files and employment history")
    except Exception:
        logger.debug("Legacy CLI job `get_s3_files` not available", exc_info=True)
    return entries

def _discover_jobs() -> Dict[str, JobDefinition]:
    """Discover job modules under the `data_pipeline.jobs` package.

    Conventions supported (in order):
      - module exposes a `JOB` variable of type JobDefinition
      - module exposes `get_job_definition()` -> JobDefinition
      - module exposes an `entrypoint` callable and optional module docstring

    Module names starting with underscore or named 'registry' are ignored.
    """
    entries: Dict[str, JobDefinition] = {}
    try:
        jobs_pkg = importlib.import_module("data_pipeline.jobs")
    except Exception:
        logger.debug("No data_pipeline.jobs package available for discovery", exc_info=True)
        return entries

    for finder, name, ispkg in pkgutil.iter_modules(jobs_pkg.__path__):
        if name.startswith("_") or name == "registry":
            continue
        full_name = f"data_pipeline.jobs.{name}"
        try:
            mod = importlib.import_module(full_name)
        except Exception:
            logger.warning("Failed to import job module %s", full_name, exc_info=True)
            continue

        # Priority: JOB var -> get_job_definition() -> entrypoint callable
        job_def = None
        if hasattr(mod, "JOB"):
            candidate = getattr(mod, "JOB")
            if isinstance(candidate, JobDefinition):
                job_def = candidate
        if job_def is None and hasattr(mod, "get_job_definition"):
            try:
                candidate = mod.get_job_definition()
                if isinstance(candidate, JobDefinition):
                    job_def = candidate
            except Exception:
                logger.warning("get_job_definition() failed for %s", full_name, exc_info=True)
        if job_def is None and hasattr(mod, "entrypoint") and callable(getattr(mod, "entrypoint")):
            desc = (mod.__doc__ or "").strip().splitlines()[0] if mod.__doc__ else ""
            job_def = JobDefinition(entrypoint=getattr(mod, "entrypoint"), description=desc or name)

        if job_def:
            # Use module name as the job key unless the module provides a preferred name via description
            entries[name] = job_def

    return entries

def get_registry() -> Dict[str, JobDefinition]:
    """Return a registry of available jobs.

    This implementation supports dynamic discovery of job modules under
    `data_pipeline.jobs` while preserving a small set of legacy CLI-backed jobs.
    """
    registry: Dict[str, JobDefinition] = {}
    # Load legacy CLI-backed entries first (keeps stable names)
    registry.update(_load_static_cli_entries())
    # Discover package-based jobs
    registry.update(_discover_jobs())
    return registry
