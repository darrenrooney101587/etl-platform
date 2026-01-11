# reporting_seeder

Daily materialized view refresh for agency reporting queries (custom + canned). Exposes CLI jobs to run all agencies, a single agency, or a specific manifest entry.

## Layout
- `cli/`: console entrypoint and job wiring (via `etl_core.cli` helpers).
- `jobs/`: job definitions exporting `JOB` tuples.
- `processors/`: orchestration and parallel execution logic.
- `repositories/`: SQL for manifests/materialized views/history tables.
- `tests/`: unit tests using unittest + DI for DB clients.

## Env
- Uses shared external Postgres on host `localhost` port `5432` by default. Override with `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`.
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

## Notes
- Jobs orchestrate; processors handle concurrency and circuit breaking; repositories hold SQL for manifests/materialized views/history tables.
- Infra and Docker live outside this package (see `infra/reporting_seeder` and `docker/reporting-seeder.Dockerfile`).
