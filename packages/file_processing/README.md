# file_processing

Data quality validation and file processing pipeline for S3 objects.

## Overview

`file_processing` implements the backend data-quality and profiling pipeline that:

- Accepts S3 object-created notifications (via SNS in production; a small HTTP listener is available for dev).
- Downloads and parses files (CSV, JSONL, Parquet).
- Validates data against pinned schema definitions.
- Computes data-quality scores using proportional deductions.
- Generates profiling payloads (statistical summaries, completeness, uniqueness, distributions, bounds anomalies, samples).
- Persists results to the shared `reporting.*` Postgres schema.

This package is designed to run inside EKS jobs or long-running workers that receive SNS notifications and execute the `s3_data_quality_job` logic.

## Layout (short)

- `cli/` — package console entrypoints (`file-processing`, `file-processing-sns`).
- `jobs/` — job entry modules (export `JOB = (entrypoint, description)`).
- `parsers/` — file parsers (CSV/JSONL/Parquet).
- `processors/` — business logic (profiling, validators, scoring).
- `validators/` — individual validation rules (schema, completeness, uniqueness, bounds).
- `repositories/` — DB queries for monitoring files, runs, profiles, and quality results.
- `tests/` — unit tests for all components.

## Jobs and discovery

Jobs must export a `JOB` tuple. The CLI discovers available jobs and exposes a `run` command:

- `file-processing list` — list jobs
- `file-processing run <job_name> [args...]` — run a job
- `file-processing help <job_name>` — job help

The primary job in this package is `s3_data_quality_job` (processes S3 object events for DQ/profiling).

Job contract (recommended): export a `JOB = (entrypoint, description)` where `entrypoint(argv: List[str]) -> int`.

## CLI / SNS listener

- `file-processing` — main CLI for invoking jobs locally or inside containers.
- `file-processing-sns` — small HTTP listener that accepts SNS `SubscriptionConfirmation` and `Notification` POSTs and forwards the message to the job pipeline (dev use).

The SNS listener wraps the SNS envelope and calls the job entrypoint with a synthetic event so the same event parsing logic is reused.

## S3 key format

The pipeline expects S3 keys that include routing metadata. The most common formats supported (parser is tolerant and also supports shorter keys for development):

- Strict canonical (production):

  `agency/<agency_slug>/files/<file_name>/<YYYY-MM-DD>/<HH>/data.<ext>`

  Example: `agency/tenant-a/files/daily-report/2026-01-04/12/data.csv`

- S3 notification keys may be nested under a prefix (for example `from_client/...`). For local development you can set `LOCAL_S3_ROOT` and pass keys relative to that root.

The job extracts these fields from the key: `agency_slug`, `file_name`, optional `run_date` and `run_hour` when present.

## Data Quality scoring (summary)

- Starting score: 100
- Proportional deductions are applied per-category. Categories and maxima:
  - Schema: max 40 (required columns, type mismatches)
  - Format: max 35 (parse errors)
  - Completeness: max 20 (nulls in required fields)
  - Bounds: max 15 (values outside min/max)
  - Uniqueness: max 10 (duplicate values for columns marked `unique`)

Score computation (backend):
- Each validator reports `failed_checks` and `total_checks` (or an equivalent failure ratio).
- Deduction = (failure_ratio) * category_max
- Final score = clamp(round(100 - sum(deductions)), 0, 100)
- Pass threshold = score >= 80

Refer to `packages/file_processing/constants.ts` (frontend helper) for formulas used in tooltips.

### Uniqueness semantics (important)

- The pipeline no longer uses a concept of `primary_key` or `identity` columns for profiling/duplicate detection.
- Uniqueness checks are driven solely by the schema flags (`unique: true` on column definitions or `unique_keys` lists when present).
- Per-column uniqueness:
  - Null-like values are ignored when computing unique counts and duplicate percentages. Null-like values are: `None`, empty/whitespace strings, or the literal string `"null"` (case-insensitive).
  - Cardinality is reported as the percentage of unique, non-null values across rows.
- Full-row duplicates (profiling duplicates):
  - Full-row duplicates are computed by comparing tuples of row values across all file columns (the profiler no longer excludes any column by default). Two rows are duplicates only if every column value is equal after the profiler's null normalization.
  - The UI shows: `Total Rows`, `Unique Rows`, `Duplicates` (count), `Duplicate %` (duplicates / totalRows * 100).

This separation keeps vertical per-column uniqueness (for `unique` constraints) distinct from horizontal full-row duplicate detection used for profiling.

## Profiling classification rules

For each column the profiler produces a single entry. Which metrics appear depends on whether the column is treated as numeric or categorical:

- Schema precedence: if the pinned schema marks a column numeric (`integer`, `float`, `decimal`, `number`, etc.), the profiler treats it as numeric and computes numeric statistics (mean, median, stdDev, min, max, outliers, etc.).
- Heuristic fallback: if schema type is not present, the profiler will attempt to coerce non-null values to numbers. The column is treated as numeric only when at least 80% of non-null values parse as numbers; otherwise it is treated as categorical.

Notes:
- The profiler treats the string values `null`, empty, and whitespace-only as nulls.
- For categorical columns the profiler produces a histogram (when cardinality is small enough) and per-column duplicate counts.
- `iqr` field is not emitted in the statistical summary (frontend doesn't use it).

## Schema examples

A schema definition is a JSON stored in your monitoring schema tables. Minimal example:

```json
{
  "columns": [
    {"name": "record_id", "type": "integer", "unique": true, "required": true},
    {"name": "badge_number", "type": "string", "required": true},
    {"name": "hours", "type": "decimal", "min": 0, "required": true}
  ],
  "unique_keys": ["record_id"]
}
```

Supported types: `string`, `integer`, `float`, `decimal`, `boolean`, `date`, `datetime`.

## Configuration (.env)

Create `packages/file_processing/.env` for local development. Recommended variables:

- `LOCAL_S3_ROOT` — when set, the processor will read local files under this path instead of S3 (useful for dev and dry runs).
- `DATABASE_URL` or `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` — database config used by `etl_core.database.client`.
- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` — only needed when the S3Client will interact with real S3.
- `PORT` — port for the SNS HTTP listener (default 8080).

**Tip**: commit a `packages/file_processing/.env.example` with placeholder values and copy it to `.env` locally.

## Docker and local runs

Dockerfiles are in `docker/` and expect you run `docker build` from the repository root so `COPY packages/...` statements succeed.

- Build file-processing image:

```bash
docker build -f docker/file-processing.Dockerfile -t etl-file-processing .
```

- Run s3 DQ job (dry-run) with mounted repo and local `.env`:

```bash
docker run --rm -v "$PWD":/app -w /app \
  --env-file packages/file_processing/.env \
  -e DB_HOST=host.docker.internal \
  -e PYTHONPATH=/app/packages \
  etl-file-processing \
  run s3_data_quality_job -- \
    --event-json '{"Records": [{"s3": {"bucket": {"name": "ignored"}, "object": {"key": "from_client/nm_albuquerque/Officer_Detail.csv"}}}]}' \
    --dry-run --dry-run-output ./dry_run_results.jsonl -v
```

- Run SNS HTTP listener inside the image:

```bash
docker run --rm -it -v "$PWD":/app -w /app \
  --env-file packages/file_processing/.env \
  -e PORT=8080 -e PYTHONPATH=/app/packages \
  --entrypoint python \
  etl-file-processing -m file_processing.cli.sns_main
```

See `scripts/commands.sh` for a curated set of copy/paste commands.

## Testing

Run unit tests for this package:

```bash
python -m pytest packages/file_processing/tests/unit -v
```

All validators and processors include unit tests; tests use DI-friendly fakes for the repository and S3 client.

## Adding new jobs, validators, or parsers

- Jobs: add a module under `jobs/` and export `JOB = (entrypoint, description)`.
- Validators: add a new class under `validators/` implementing `BaseValidator` and register it in `_run_validations` inside the processor.
- Parsers: add a parser under `parsers/` and register it in `parsers/registry.py`.

## Troubleshooting & notes

- If you receive `ModuleNotFoundError: No module named 'file_processing'` when running in Docker, ensure `PYTHONPATH=/app/packages` is set and that you built the image from the repository root.
- Use `LOCAL_S3_ROOT` for development to avoid S3 credentials and to debug against local files.
- The profiler treats `null` / empty / whitespace-only as null values which are ignored for per-column uniqueness calculations but are part of full-row comparisons when values are equal across rows.

---

If you want, I can also add a short section with example SNS subscription steps (how to configure topic -> HTTPS subscription) or create a small `docker-compose` for local SNS testing behind an HTTP tunnel. Ask if you'd like either of those added.
