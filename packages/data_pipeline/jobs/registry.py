from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from packages.data_pipeline.jobs import healthcheck


@dataclass(frozen=True)
class JobSpec:
    name: str
    description: str
    entrypoint: Callable[[list[str]], int]


def get_registry() -> dict[str, JobSpec]:
    return {
        "healthcheck": JobSpec(
            name="healthcheck",
            description="Healthcheck placeholder job",
            entrypoint=healthcheck.main,
        )
    }
