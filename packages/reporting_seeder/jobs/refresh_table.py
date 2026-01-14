from __future__ import annotations

import argparse
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

DESCRIPTION = "Refresh a single manifest entry by table name"


def entrypoint(argv: List[str]) -> int:
    """Refresh a single manifest entry by table name."""
    parser = argparse.ArgumentParser(prog="refresh_table")
    parser.add_argument("table_name", help="Fully qualified table name to refresh")
    args = parser.parse_args(argv)

    config = SeederConfig.from_env()

    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "reporting_seeder.settings")

    try:
        bootstrap_django(settings_module)
    except Exception:
        logger.exception("Failed to bootstrap Django using %s", settings_module)
        raise

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
    processor.refresh_table(args.table_name)
    return 0


JOB = (entrypoint, DESCRIPTION)
