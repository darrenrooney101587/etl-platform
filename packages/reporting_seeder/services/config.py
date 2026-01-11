"""Runtime configuration for reporting_seeder.

Values are sourced from environment variables with safe defaults to support
local development against the shared Postgres on host 5432.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class SeederConfig:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    max_workers: int
    max_failures: int
    reset_seconds: int
    refresh_concurrently: bool

    @classmethod
    def from_env(cls) -> "SeederConfig":
        return cls(
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_name=os.getenv("DB_NAME", "postgres"),
            db_user=os.getenv("DB_USER", "postgres"),
            db_password=os.getenv("DB_PASSWORD", ""),
            max_workers=int(os.getenv("SEEDER_MAX_WORKERS", "8")),
            max_failures=int(os.getenv("SEEDER_MAX_FAILURES", "5")),
            reset_seconds=int(os.getenv("SEEDER_RESET_SECONDS", "300")),
            refresh_concurrently=os.getenv("SEEDER_REFRESH_CONCURRENTLY", "false").lower() == "true",
        )
