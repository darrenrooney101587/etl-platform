import argparse
from typing import List

from etl_core.support.circuit_breaker import CircuitBreaker
from etl_core.support.executor import ParallelExecutor
from reporting_seeder.processors.refresh import RefreshProcessor
from reporting_seeder.repositories.manifests import ManifestRepository
from reporting_seeder.repositories.history import HistoryRepository
from reporting_seeder.repositories.materialized_views import MaterializedViewRepository
from reporting_seeder.services.config import SeederConfig
from packages.etl_core.database.client import DatabaseClient


DESCRIPTION = "Refresh all enabled manifest entries for a single agency"


def entrypoint(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="refresh_agency")
    parser.add_argument("agency_slug", help="Agency slug to refresh")
    args = parser.parse_args(argv)

    config = SeederConfig.from_env()
    db_client = DatabaseClient()
    manifest_repo = ManifestRepository(db_client)
    history_repo = HistoryRepository(db_client)
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
    processor.refresh_agency(args.agency_slug)
    return 0


JOB = (entrypoint, DESCRIPTION)
