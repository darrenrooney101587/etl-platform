"""Deferred Django bootstrap and a tiny Django-backed DB client adapter.

This file is intended as an example for developers. It lives inside the
`reporting_seeder` package so other packages can import it at runtime.

Design goals:
- Do NOT import Django at module import time. Imports are deferred to runtime
  so test suites that don't have Django installed continue to work.
- Provide `bootstrap_django(settings_module)` to set DJANGO_SETTINGS_MODULE
  and call `django.setup()`.
- Provide `DjangoORMClient` with `execute_query`, `fetch_all`, and `close`
  that use `django.db.connection` under the hood.

Usage examples (direct):
    from reporting_seeder.django_bootstrap import bootstrap_django, DjangoORMClient
    bootstrap_django('reporting_models.settings')
    db = DjangoORMClient()
    rows = db.fetch_all('SELECT 1 AS x')

Usage via etl_core factory:
    export DJANGO_DB_CLIENT_PATH=reporting_seeder.django_bootstrap:DjangoORMClient
    from etl_core.support.db_factory import get_database_client
    db = get_database_client()  # will instantiate DjangoORMClient

"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import os


def bootstrap_django(settings_module: str) -> None:
    """Set `DJANGO_SETTINGS_MODULE` and initialize Django.

    This defers importing Django until the function is called so importing
    this module does not require Django to be installed.

    Args:
        settings_module: Python module path for Django settings (e.g. 'reporting_models.settings').

    Raises:
        RuntimeError: if DJANGO_SETTINGS_MODULE is already set to a different value.
    """
    current = os.environ.get("DJANGO_SETTINGS_MODULE")
    if current and current != settings_module:
        raise RuntimeError(
            f"DJANGO_SETTINGS_MODULE already set to '{current}', expected '{settings_module}'"
        )

    # Deferred import
    try:
        from django import setup as django_setup  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("Django must be installed to bootstrap the ORM") from exc

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)
    django_setup()


class DjangoORMClient:
    """Small adapter exposing execute/fetch/close backed by Django's DB connection.

    Important: `bootstrap_django(...)` must be called before instantiating this
    class so Django is configured.
    """

    def __init__(self) -> None:
        # No-op; django.setup() must have been invoked prior to instantiation
        pass

    def execute_query(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> None:
        """Execute a non-SELECT statement (INSERT/UPDATE/DELETE/DDL).

        Raises DB exceptions on failure.
        """
        # Deferred import to avoid requiring Django during normal test runs
        from django.db import connection  # type: ignore

        with connection.cursor() as cur:
            cur.execute(sql, params or ())

    def fetch_all(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> List[Dict[str, Any]]:
        """Execute a SELECT statement and return rows as list[dict]."""
        from django.db import connection  # type: ignore

        with connection.cursor() as cur:
            cur.execute(sql, params or ())
            cols = [c[0] for c in cur.description] if cur.description else []
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return rows

    def close(self) -> None:
        """Close the Django DB connection (safe to call multiple times)."""
        try:
            from django.db import connection  # type: ignore

            connection.close()
        except Exception:
            pass


class AutoDjangoClient(DjangoORMClient):
    """DjangoORMClient that bootstraps Django automatically from DJANGO_SETTINGS_MODULE.

    This is convenient when using the `etl_core.support.db_factory` which
    instantiates the class without arguments. AutoDjangoClient will look for
    the `DJANGO_SETTINGS_MODULE` environment variable and call `bootstrap_django`.
    """

    def __init__(self) -> None:
        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")
        if not settings_module:
            raise RuntimeError(
                "DJANGO_SETTINGS_MODULE env var is not set. Set it or call bootstrap_django() before using AutoDjangoClient"
            )
        # bootstrap will import django and call django.setup()
        bootstrap_django(settings_module)
        super().__init__()
