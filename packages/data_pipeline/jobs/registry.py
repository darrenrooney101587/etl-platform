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
    return entries


def _discover_jobs() -> Dict[str, JobDefinition]:
    """Discover job modules under the `data_pipeline.jobs` package.

    New convention (single source of truth):
      - module must expose a `JOB` variable of type JobDefinition

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

        # Strict convention: module must expose JOB = JobDefinition(...)
        if hasattr(mod, "JOB"):
            candidate = getattr(mod, "JOB")
            # Accept explicit JobDefinition instances
            if isinstance(candidate, JobDefinition):
                entries[name] = candidate
            # Accept a lightweight tuple form (callable, description) to avoid circular imports in job modules
            elif isinstance(candidate, (list, tuple)) and len(candidate) == 2 and callable(candidate[0]) and isinstance(
                    candidate[1], str):
                entries[name] = JobDefinition(entrypoint=candidate[0], description=candidate[1])
            else:
                logger.warning("JOB in %s is not a JobDefinition or tuple(entrypoint, description); ignoring",
                               full_name)
        else:
            logger.warning("Job module %s does not expose JOB; ignoring (migrate to JOB variable)", full_name)

    return entries


def get_registry() -> Dict[str, JobDefinition]:
    """Return a registry of available jobs.

    This implementation supports discovery of job modules under
    `data_pipeline.jobs` and expects each module to expose a `JOB` variable.
    """
    registry: Dict[str, JobDefinition] = {}
    # Load legacy CLI-backed entries first (keeps stable names)
    registry.update(_load_static_cli_entries())
    # Discover package-based jobs
    registry.update(_discover_jobs())
    return registry
