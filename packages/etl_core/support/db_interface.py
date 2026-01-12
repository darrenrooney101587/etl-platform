"""Database client interface and adapters for etl_core.

This module defines a minimal runtime interface for DB clients so packages can
supply either the existing psycopg2-backed `DatabaseClient` or a Django-backed
adapter. etl_core must not import Django; implementations that require Django
should live in package-level modules and be loaded via the factory.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class DatabaseClientProtocol(Protocol):
    """Minimal database client protocol used across packages.

    Implementations should provide an `execute_query(sql, params)` method that
    returns a list of dict rows for SELECT/RETURNING queries and an optional
    `close()` method.
    """

    def execute_query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:  # pragma: no cover - interface
        ...

    def close(self) -> None:  # pragma: no cover - interface
        ...
