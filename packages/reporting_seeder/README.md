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

## Release snapshots (schema/shape drift)
Release snapshots capture immutable schema/shape metadata for a materialized view at a specific release tag. This is separate from Job History: job history tracks execution runs, while release snapshots record the schema/shape state of the view at a release.

Snapshots are persisted in `reporting.seeder_release_snapshot` and include schema hashes, row/column counts, per-column null/distinct stats, and optional top-value distributions. Drift comparisons are computed in the backend so the UI does not need to diff snapshots itself.

Capture a release snapshot:

```bash
cd packages/reporting_seeder
poetry run python -m cli.main run capture_release_snapshot -- \
  --table-name reporting.reports \
  --release-tag abc123 \
  --release-version v1.2.3 \
  --top-values-columns status,category
```

Service helpers for APIs live in `reporting_seeder.services.release_snapshots`:
- `list_release_snapshots_by_table(table_name, limit=50)`
- `compare_release_snapshots_by_id(base_snapshot_id, compare_snapshot_id)`

## Recent behavior & important operator notes
This package was updated to make materialized-view refreshes robust and operator-friendly for production usage. Key points:

- The seeder now distinguishes between two refresh modes:
  - Non-concurrent refresh (default and safe): `REFRESH MATERIALIZED VIEW <view>` — takes an exclusive lock on the materialized view while refreshing. Use during a low-traffic maintenance window.
  - Concurrent refresh (Postgres `CONCURRENTLY`): `REFRESH MATERIALIZED VIEW CONCURRENTLY <view>` — avoids exclusive locking but requires the materialized view to have a unique index with no WHERE clause. When concurrent refresh is enabled, the seeder will attempt it and automatically fall back to non-concurrent refresh if PostgreSQL reports the unique index prerequisite is not met.

- Auto-creation of unique indexes has been intentionally removed. Creating a correct unique index requires domain knowledge about the view's data; automatically guessing a unique key is unsafe. Operators should create appropriate unique indexes via migrations or manual SQL when concurrent refresh is required.

- The `has_unique_index` check has been removed from the codebase. We cannot guarantee that each materialized view will have a unique index. The refresh logic now relies on PostgreSQL's runtime error handling: when concurrent refresh is attempted on a view without a unique index, PostgreSQL raises an error which is caught and triggers an automatic fallback to non-concurrent refresh.

- The processor collects PostgreSQL-side metrics (via `pg_stat_statements` / `pg_stat_activity`) where available, and records these in the seeder history tables so the team can observe DB-side cost (I/O, time) for each manifest.

## Throttling, leveling, and safety levers
To avoid flooding the database, the seeder exposes several environment-configurable levers. These are designed to be conservative by default and let you tune how aggressively the job submits/executes refreshes.

Environment variables (defaults shown)

- `DB_HOST` (default: `localhost`) — Postgres host
- `DB_PORT` (default: `5432`) — Postgres port
- `DB_NAME` (default: `postgres`) — Postgres database name
- `DB_USER` / `DB_PASSWORD` — DB credentials

- `SEEDER_MAX_WORKERS` (default: `8`) — number of worker threads in the thread pool (true concurrent refresh limit). Lower to reduce concurrent DB connections.
- `SEEDER_BATCH_SIZE` (default: `8`) — number of manifests submitted per batch. Submission rate is controlled by batching; the executor still enforces `SEEDER_MAX_WORKERS` for concurrent execution.
- `SEEDER_START_DELAY_MS` (default: `0`) — milliseconds to wait between submitting batches. Use to spread load over time.
- `SEEDER_MAX_DB_ACTIVE_QUERIES` (default: `0` = disabled) — when > 0 the processor polls `pg_stat_activity` before submitting each batch and waits while the total active (non-idle) DB queries are >= this threshold. This is a conservative DB-aware throttle across the whole DB instance.
- `SEEDER_MAX_FAILURES` (default: `5`) — how many consecutive failures before the internal circuit breaker opens and stops new work temporarily.
- `SEEDER_RESET_SECONDS` (default: `300`) — cooldown seconds after the circuit breaker opens.
- `SEEDER_REFRESH_CONCURRENTLY` (default: `false`) — when enabled, attempt concurrent refresh for all views. If a view lacks the required unique index, PostgreSQL will fail the concurrent refresh and the seeder will automatically fall back to non-concurrent refresh.

Recommended conservative example for shared production DBs

- `SEEDER_MAX_WORKERS=4`
- `SEEDER_BATCH_SIZE=2`
- `SEEDER_START_DELAY_MS=500` (0.5s)
- `SEEDER_MAX_DB_ACTIVE_QUERIES=20`
- `SEEDER_REFRESH_CONCURRENTLY=false` (unless you have inspected and created unique indexes)

These settings reduce concurrency and submit rate, and add a small spacing between batches to avoid sudden bursts.

## Observability / postgres-side metrics
- The seeder attempts to collect metrics from `pg_stat_statements` (if installed) and `pg_stat_activity`. These provide:
  - `calls`, `total_exec_time`, `mean_exec_time`, `rows`, and block I/O counters (when `pg_stat_statements` is available).
  - Current active query information (from `pg_stat_activity`) used by the DB-aware throttle.
- We recommend enabling `pg_stat_statements` on the RDS/PG server to improve visibility. If it is not available the seeder logs will still work but postgres-side metrics will be absent.

## Quickstart (local)
```bash
cd packages/reporting_seeder
poetry install --no-interaction --no-ansi
# Run a conservative local test (adjust env as needed)
SEEDER_MAX_WORKERS=4 SEEDER_BATCH_SIZE=2 SEEDER_START_DELAY_MS=500 SEEDER_MAX_DB_ACTIVE_QUERIES=20 \
  SEEDER_REFRESH_CONCURRENTLY=false \
  poetry run python -m cli.main run refresh_all
```

## Running jobs
```bash
# Preferred (quick) — run from the package directory using the package module
# This does not require installing the package as a script and is safe for local/dev runs
cd packages/reporting_seeder
# Run all manifests (default)
poetry run python -m cli.main run refresh_all

# Run only custom manifests
poetry run python -m cli.main run refresh_all -- --report-type custom

# Run only canned manifests
poetry run python -m cli.main run refresh_all -- --report-type canned

# Or, if you prefer to install the package entrypoint so `reporting-seeder` is available:
# 1) install the package (creates the script entrypoint)
cd packages/reporting_seeder
poetry install --no-interaction --no-ansi
# 2) run the installed entrypoint
poetry run reporting-seeder run refresh_all
```

Note: you saw a warning like "Warning: 'reporting-seeder' is an entry point defined in pyproject.toml, but it's not installed as a script" because you tried to run the entrypoint without installing the package. Use the first (module) option for quick runs, or run `poetry install` in the package directory once to enable the `reporting-seeder` command.

```bash
# Run a single agency by slug (recommended module run)
cd packages/reporting_seeder
poetry run python -m cli.main run refresh_agency demo

# Or, if you have installed the package entrypoint via `poetry install`:
poetry run reporting-seeder run refresh_agency demo

# Run a specific manifest record by table name (recommended module run)
cd packages/reporting_seeder
poetry run python -m cli.main run refresh_table reporting.reports

# Or, if installed:
poetry run reporting-seeder run refresh_table reporting.reports
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

## Local Docker development (recommended)

`reporting_seeder` requires:
- `etl_core` (local monorepo package)
- `etl_database_schema` (private schema package)

To avoid pulling `etl-database-schema` from GitLab during every Docker build (VPN dependency), the local workflow uses a sibling checkout staged into the Docker build context.

1) One-time: clone the schema repo next to this repo:
```bash
git clone git@gitlab.dev-benchmarkanalytics.com:etl/etl-database-schema.git ../etl-database-schema
```

2) Build the local image (stages schema into `.local/etl-database-schema` and builds from repo root):
```bash
./packages/reporting_seeder/scripts/build.sh
```

3) Run the container locally:

 Show CLI help:
 ```bash
 docker run --rm etl-reporting-seeder --help
 ```
 
 Run a job (examples):
 ```bash
 # List jobs
 docker run --rm etl-reporting-seeder list
 
 # Run refresh_all using the per-package .env (recommended)
 docker run --rm \
   etl-reporting-seeder run refresh_all
 ```

Optional: override a variable without editing `.env` (common on macOS when connecting to host Postgres):
```bash
docker run --rm \
  --env-file packages/reporting_seeder/.env \
  -e DB_HOST=host.docker.internal \
  etl-reporting-seeder run refresh_all
```

By default, this expects the schema repo to be checked out next to the repo root at `../etl-database-schema`.
If your clone lives elsewhere, pass an explicit path:
```bash
./packages/reporting_seeder/scripts/build.sh --schema-path /absolute/path/to/etl-database-schema
```

### Updating code and schema (local dev)

You do not need to re-clone `etl-database-schema` each time.

- If `etl-platform` changes (this repo): pull and rebuild the image.
- If `etl-database-schema` changes: `git pull` in the sibling checkout and rebuild the image.

Example:
```bash
# Update this repo
git pull

# Update the schema repo (sibling to this repo)
cd ../etl-database-schema && git pull

# Rebuild the local image (restages schema into .local/ and rebuilds)
cd -
./packages/reporting_seeder/scripts/build.sh
```

## Notes
- Jobs orchestrate; processors handle concurrency and circuit breaking; repositories hold SQL for manifests/materialized views/history tables.
- Tests should use DI to inject fakes/mocks for DB/S3/other external resources.
- Infra and Docker live outside this package (see `infra/reporting_seeder` and `docker/reporting-seeder.Dockerfile`).
