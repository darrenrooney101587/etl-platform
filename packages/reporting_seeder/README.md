# reporting_seeder

Daily materialized view refresh for agency reporting queries (custom + canned). Exposes CLI jobs to run all agencies, a single agency, or a specific manifest entry.

## Layout
- `cli/`: console entrypoint and job wiring (via `etl_core.cli` helpers).
- `jobs/`: job definitions exporting `JOB` tuples.
- `processors/`: orchestration and parallel execution logic.
- `repositories/`: SQL for manifests/materialized views/history tables.
- `tests/`: unit tests using `unittest.TestCase` and DI for DB clients.

## Purpose / responsibilities
- Jobs: orchestration and operational surface only. Jobs must export a top-level `JOB` tuple: `(entrypoint, description)` where `entrypoint(argv: List[str]) -> int`.
- Processors: reusable business logic (concurrency, circuit breaking, transforms). Accept typed dataclasses and client dependencies via constructor injection.
- Repositories: contain domain SQL and data-shaping logic; accept a `DatabaseClient` via constructor injection.

## Environment
- Uses shared Postgres (defaults): host `localhost`, port `5432`. Override with `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`.
- Optional circuit-breaker tuning via `SEEDER_MAX_FAILURES` and `SEEDER_RESET_SECONDS`.

## Quickstart (local)
```bash
cd packages/reporting_seeder
poetry install --no-interaction --no-ansi
poetry run reporting-seeder list
```

## Running jobs
```bash
# Run all enabled agencies (parallelized)
poetry run reporting-seeder run refresh_all

# Run a single agency by slug
poetry run reporting-seeder run refresh_agency -- gotham

# Run a specific manifest record by table name
poetry run reporting-seeder run refresh_table -- reporting.stg_arrests
```

## Using the Django ORM (developer example)

If you have an upstream package that provides Django settings and models (for example `packages/reporting_models`), you can bootstrap Django at runtime and use a Django-backed DB client.

Example helper `reporting_seeder.django_bootstrap` exposes `bootstrap_django` and `DjangoORMClient`.

Direct bootstrap example:

```python
from reporting_seeder.django_bootstrap import bootstrap_django, DjangoORMClient
# Ensure your reporting_models.settings exists and is importable
bootstrap_django("reporting_models.settings")
db = DjangoORMClient()
rows = db.fetch_all("SELECT id, name FROM reporting.some_table LIMIT 10")
```

Factory usage (swap clients via env var):

```bash
export DJANGO_DB_CLIENT_PATH=reporting_seeder.django_bootstrap:DjangoORMClient
```

Code that uses `etl_core.support.db_factory.get_database_client()` will instantiate the configured client lazily. Importing `reporting_seeder.django_bootstrap` does not itself import Django; heavy imports are deferred until `bootstrap_django` or `DjangoORMClient` is used.

## Notes
- Jobs orchestrate; processors handle concurrency and circuit breaking; repositories hold SQL for manifests/materialized views/history tables.
- Tests should use DI to inject fakes/mocks for DB/S3/other external resources.
- Infra and Docker live outside this package (see `infra/reporting_seeder` and `docker/reporting-seeder.Dockerfile`).
