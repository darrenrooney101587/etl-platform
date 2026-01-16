"""Job entrypoint for capturing release snapshots."""
from __future__ import annotations

import argparse
import logging
import os
from typing import List, Optional

from etl_core.database.client import DatabaseClient
from reporting_seeder.django_bootstrap import bootstrap_django
from reporting_seeder.processors.release_snapshots import ReleaseSnapshotProcessor
from reporting_seeder.repositories.manifests import ManifestRepository
from reporting_seeder.repositories.materialized_views import MaterializedViewRepository
from reporting_seeder.repositories.release_snapshots import ReleaseSnapshotRepository
from reporting_seeder.services.config import SeederConfig

logger = logging.getLogger(__name__)

DESCRIPTION = "Capture a release snapshot for a reporting materialized view"


def entrypoint(argv: List[str]) -> int:
    """Capture a release snapshot for a manifest table.

    :param argv: CLI args.
    :type argv: List[str]
    :returns: Process exit code.
    :rtype: int
    """
    parser = argparse.ArgumentParser(prog="capture_release_snapshot")
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--table-name", help="Fully qualified table name to snapshot")
    target_group.add_argument("--manifest-id", type=int, help="Manifest id to snapshot")
    parser.add_argument(
        "--release-tag",
        help="Release tag or git SHA (defaults to GIT_SHA/CI_COMMIT_SHA env var)",
    )
    parser.add_argument("--release-version", help="Optional release version string")
    parser.add_argument(
        "--top-values-columns",
        help="Comma-delimited allowlist of columns for top-values stats",
    )
    args = parser.parse_args(argv)

    release_tag = args.release_tag or os.getenv("GIT_SHA") or os.getenv("CI_COMMIT_SHA")
    if not release_tag:
        raise ValueError("release_tag is required; set --release-tag or GIT_SHA/CI_COMMIT_SHA")

    config = SeederConfig.from_env()
    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "reporting_seeder.settings")

    try:
        bootstrap_django(settings_module)
    except Exception:
        logger.exception("Failed to bootstrap Django using %s", settings_module)
        raise

    db_client = DatabaseClient()
    manifest_repo = ManifestRepository(db_client)
    mv_repo = MaterializedViewRepository(db_client)
    snapshot_repo = ReleaseSnapshotRepository(db_client)
    processor = ReleaseSnapshotProcessor(snapshot_repo)

    manifest = _resolve_manifest(manifest_repo, args.table_name, args.manifest_id)
    if not manifest:
        logger.error("No manifest found for requested target")
        return 1

    table_name = str(manifest["table_name"])
    refresh_concurrently = config.refresh_concurrently and mv_repo.has_unique_index(table_name)
    mv_repo.refresh_view(table_name, concurrently=refresh_concurrently)
    mv_repo.analyze_view(table_name)

    allowlist = _parse_csv(args.top_values_columns)
    try:
        processor.capture_snapshot(
            manifest=manifest,
            release_tag=release_tag,
            release_version=args.release_version,
            top_values_columns=allowlist,
        )
    except Exception:
        logger.exception("Failed to capture release snapshot for %s", table_name)
        return 1

    logger.info("Release snapshot captured for %s", table_name)
    return 0


def _resolve_manifest(
    repository: ManifestRepository, table_name: Optional[str], manifest_id: Optional[int]
) -> Optional[dict]:
    """Fetch a manifest using table name or manifest id.

    :param repository: Manifest repository.
    :type repository: ManifestRepository
    :param table_name: Table name when provided.
    :type table_name: Optional[str]
    :param manifest_id: Manifest id when provided.
    :type manifest_id: Optional[int]
    :returns: Manifest row or None.
    :rtype: Optional[dict]
    """
    if manifest_id is not None:
        return repository.get_manifest_by_id(manifest_id)
    if table_name:
        return repository.get_manifest_by_table(table_name)
    return None


def _parse_csv(value: Optional[str]) -> List[str]:
    """Parse a comma-delimited list of values.

    :param value: CSV string to parse.
    :type value: Optional[str]
    :returns: List of trimmed values.
    :rtype: List[str]
    """
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


JOB = (entrypoint, DESCRIPTION)
