"""Skeleton CloverDX ingestion job."""
from __future__ import annotations

from typing import List

from observability.bootstrap import bootstrap
from observability.services.grouping import SignalService


def entrypoint(argv: List[str]) -> int:
    bootstrap()
    # TODO: implement CloverDX ingestion
    SignalService()
    return 0


JOB = (entrypoint, "Ingest CloverDX signals into notification tables")
