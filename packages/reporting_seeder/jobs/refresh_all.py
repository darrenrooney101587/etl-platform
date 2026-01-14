from __future__ import annotations

import logging
import os
from typing import List

from etl_core.database.client import DatabaseClient
from etl_core.support.circuit_breaker import CircuitBreaker
from etl_core.support.executor import ParallelExecutor
from reporting_seeder.django_bootstrap import bootstrap_django
from reporting_seeder.processors.refresh import RefreshProcessor
from reporting_seeder.repositories.history import HistoryRepository
from reporting_seeder.repositories.manifests import ManifestRepository
from reporting_seeder.repositories.materialized_views import MaterializedViewRepository
from reporting_seeder.services.config import SeederConfig

logger = logging.getLogger(__name__)


DESCRIPTION = "Refresh all enabled manifest entries (custom + canned) in parallel"


def entrypoint(argv: List[str]) -> int:
    """Refresh all enabled manifest entries.

    Args:
        argv: CLI args.

    Returns:
        Process exit code.
    """
    config = SeederConfig.from_env()

    # We require Django to be configured for HistoryRepository.
    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "reporting_seeder.settings")

    try:
        bootstrap_django(settings_module)
    except Exception:
        logger.exception("Failed to bootstrap Django using %s", settings_module)
        raise

    # Reduce noise from per-query DB client logging during the refresh loop.
    # The DB client logs detailed connection/activity at DEBUG; in some dev
    # environments the handler level is INFO so those calls can be noisy. Raising
    # the logger to WARNING keeps important errors while suppressing query chatter.
    try:
        import logging as _logging

        _logging.getLogger("etl_core.database.client").setLevel(_logging.WARNING)
    except Exception:
        pass

    db_client = DatabaseClient()
    manifest_repo = ManifestRepository(db_client)
    history_repo = HistoryRepository()
    mv_repo = MaterializedViewRepository(db_client)
    circuit_breaker = CircuitBreaker(
        max_failures=config.max_failures,
        reset_seconds=config.reset_seconds,
    )
    executor = ParallelExecutor(max_workers=config.max_workers)

    processor = RefreshProcessor(
        manifest_repository=manifest_repo,
        history_repository=history_repo,
        mv_repository=mv_repo,
        executor=executor,
        circuit_breaker=circuit_breaker,
        config=config,
    )
    processor.refresh_all()
    # Visible marker for automated verification in CI/local runs (prints to stdout)
    print("REFRESH_DONE")
    return 0


JOB = (entrypoint, DESCRIPTION)
