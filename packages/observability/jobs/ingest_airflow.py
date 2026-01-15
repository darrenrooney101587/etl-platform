"""Skeleton Airflow ingestion job."""
from __future__ import annotations

from typing import List

from observability.bootstrap import bootstrap
from observability.services.grouping import SignalService


def entrypoint(argv: List[str]) -> int:
    bootstrap()
    # TODO: implement Airflow ingestion
    SignalService()
    return 0


JOB = (entrypoint, "Ingest Airflow signals into notification tables")
