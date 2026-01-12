"""Factory for obtaining a DatabaseClient implementation.

Usage:
  from etl_core.support.db_factory import get_database_client
  db = get_database_client()

Behavior:
- If env var DJANGO_DB_CLIENT_PATH is set (e.g. "reporting_models.django_client:DjangoORMClient"),
  the factory will import that symbol and instantiate it. The symbol must
  implement the DatabaseClientProtocol.
- Otherwise it returns the standard etl_core.database.client.DatabaseClient.
"""
from __future__ import annotations

import importlib
import os
from typing import Any, Optional

from etl_core.support.db_interface import DatabaseClientProtocol
from etl_core.database.client import DatabaseClient as PsycopgDatabaseClient


def _load_external_client(path: str) -> Optional[DatabaseClientProtocol]:
    """Load an external DB client from a python path like 'pkg.module:ClassName'."""
    try:
        if ":" in path:
            module_path, symbol = path.split(":", 1)
        elif "." in path:
            # allow dotted.ClassName as fallback
            module_path, symbol = path.rsplit(".", 1)
        else:
            return None
        module = importlib.import_module(module_path)
        cls = getattr(module, symbol)
        return cls()  # type: ignore
    except Exception:
        return None


def get_database_client() -> DatabaseClientProtocol:
    """Return a database client instance.

    Prefers a Django-backed client when `DJANGO_DB_CLIENT_PATH` is set. Falls
    back to the standard psycopg2-based `DatabaseClient`.
    """
    path = os.getenv("DJANGO_DB_CLIENT_PATH")
    if path:
        client = _load_external_client(path)
        if client:
            return client
    # default
    return PsycopgDatabaseClient()
