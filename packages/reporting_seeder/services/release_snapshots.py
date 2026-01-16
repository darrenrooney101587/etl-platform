"""Service helpers for release snapshot API integration."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from etl_core.database.client import DatabaseClient
from reporting_seeder.processors.release_snapshots import compare_release_snapshots
from reporting_seeder.repositories.release_snapshots import ReleaseSnapshotRepository


def list_release_snapshots_by_table(
    table_name: str, limit: int = 50, db_client: Optional[DatabaseClient] = None
) -> List[Dict[str, Any]]:
    """List release snapshots for a materialized view.

    :param table_name: Fully qualified table name.
    :type table_name: str
    :param limit: Maximum number of snapshots to return.
    :type limit: int
    :param db_client: Optional DatabaseClient override.
    :type db_client: Optional[DatabaseClient]
    :returns: Snapshot rows ordered by release timestamp.
    :rtype: List[Dict[str, Any]]
    """
    repo = ReleaseSnapshotRepository(db_client or DatabaseClient())
    return repo.list_snapshots_by_table(table_name, limit=limit)


def list_release_snapshots_by_manifest(
    manifest_id: int, limit: int = 50, db_client: Optional[DatabaseClient] = None
) -> List[Dict[str, Any]]:
    """List release snapshots for a manifest id.

    :param manifest_id: Manifest primary key.
    :type manifest_id: int
    :param limit: Maximum number of snapshots to return.
    :type limit: int
    :param db_client: Optional DatabaseClient override.
    :type db_client: Optional[DatabaseClient]
    :returns: Snapshot rows ordered by release timestamp.
    :rtype: List[Dict[str, Any]]
    """
    repo = ReleaseSnapshotRepository(db_client or DatabaseClient())
    return repo.list_snapshots_by_manifest(manifest_id, limit=limit)


def compare_release_snapshots_by_id(
    base_snapshot_id: str, compare_snapshot_id: str, db_client: Optional[DatabaseClient] = None
) -> Dict[str, Any]:
    """Compare two snapshots stored in the database.

    :param base_snapshot_id: Baseline snapshot UUID.
    :type base_snapshot_id: str
    :param compare_snapshot_id: Comparison snapshot UUID.
    :type compare_snapshot_id: str
    :param db_client: Optional DatabaseClient override.
    :type db_client: Optional[DatabaseClient]
    :returns: Drift payload computed from stored snapshots.
    :rtype: Dict[str, Any]
    :raises ValueError: When either snapshot cannot be found.
    """
    repo = ReleaseSnapshotRepository(db_client or DatabaseClient())
    base_snapshot = repo.get_snapshot_by_id(base_snapshot_id)
    compare_snapshot = repo.get_snapshot_by_id(compare_snapshot_id)
    if not base_snapshot or not compare_snapshot:
        raise ValueError("Both snapshots must exist to compute drift")
    return compare_release_snapshots(base_snapshot, compare_snapshot)
