# file_processing

Data quality validation and file processing pipeline for S3 objects.

## Overview

This package provides a complete data quality pipeline that:

1. Consumes S3 object-created notifications
2. Downloads and parses files (CSV, JSONL, Parquet)
3. Validates data against schema definitions
4. Computes quality scores with proportional deductions
5. Generates profiling payloads
6. Persists results to the shared PostgreSQL database

## Package Structure

```
file_processing/
    cli/            # CLI entrypoint using centralized etl_core helpers
    jobs/           # Job entrypoints (each exports JOB tuple)
    models/         # Dataclass models for events, monitoring tables, quality results
    parsers/        # Pluggable file parsers (CSV, JSONL, Parquet)
    processors/     # Business logic for quality validation and profiling
    repositories/   # Domain SQL for database operations
    validators/     # Validation logic (schema, completeness, uniqueness, bounds)
    tests/          # Unit and integration tests
```

## Jobs

Jobs are discovered automatically by the CLI. Each job module must export a `JOB` tuple:

```python
# packages/file_processing/jobs/my_job.py
from typing import List

def entrypoint(argv: List[str]) -> int:
    # Job logic here
    return 0  # Exit code

JOB = (entrypoint, "Description of my job")
```

### Available Jobs

| Job Name | Description |
|----------|-------------|
| `s3_data_quality_job` | Process S3 objects for data quality validation |

## CLI Usage

```bash
# List available jobs
file-processing list

# Run a job
file-processing run <job_name> [job_args...]

# Show job help
file-processing help <job_name>
```

### S3 Data Quality Job Examples

```bash
# Process a single S3 object (production)
file-processing run s3_data_quality_job --bucket my-bucket --key agency/tenant/files/report/2026-01-04/12/data.csv

# Process from JSON event (production or replay)
file-processing run s3_data_quality_job --event-json '{"bucket": "my-bucket", "key": "agency/tenant/files/report/2026-01-04/12/data.csv"}'

# Batch process from events file (production replay)
file-processing run s3_data_quality_job --events-file events.json

# Verbose output
file-processing run s3_data_quality_job --bucket my-bucket --key path/to/file.csv -v
```

## SQS Consumer

The package includes a long-polling SQS consumer that forwards messages to the `s3_data_quality_job`.

```bash
# Run the SQS consumer (requires SQS_QUEUE_URL env var)
file-processing-sqs
```

## S3 Key Format

The pipeline expects S3 keys in the following format:

```
agency/<agency_slug>/files/<file_name>/<YYYY-MM-DD>/<HH>/data.<ext>
```

Example:
```
agency/tenant-a/files/daily-report/2026-01-04/12/data.csv
```

This is parsed to extract:
- `agency_slug`: `tenant-a`
- `file_name`: `daily-report`
- `run_date`: `2026-01-04`
- `run_hour`: `12`
- `file_format`: `csv`

## Data Quality Scoring

Starting score: **100**

Deductions are proportional based on failure ratio:

| Category | Max Deduction | Description |
|----------|---------------|-------------|
| Schema | 40 | Required columns, type validation |
| Format | 35 | File parsing errors |
| Completeness | 20 | Null values in required fields |
| Bounds | 15 | Values outside min/max ranges |
| Uniqueness | 10 | Duplicate values in unique keys |

**Pass threshold**: score >= 80

### Uniqueness Validation

Uniqueness checks are performed based on the pinned schema version.
- **Nulls ignored**: Values considered null (`None`, empty string, `"null"`) are ignored during uniqueness checks.
- **Required keys**: If a unique key column is marked `required: true` in the schema, missing values count as failures.
- **Business Duplicates**: The profiling step calculates "duplicate rows" by effectively ignoring columns marked as `primary_key` or `identity` in the schema. This ensures technical IDs do not mask duplication in business data.

### Proportional Deductions

Deductions are calculated proportionally. For example, if 1 of 5 schema fields fails:
- Deduction = 40 * (1/5) = 8 points
- Final score = 100 - 8 = 92 (PASSED)

## Schema Definition

Schema definitions are stored in `reporting.monitoring_file_schema_definition` and linked to monitoring files. Example:

```json
{
    "columns": [
        {"name": "id", "type": "integer", "required": true, "nullable": false, "unique": true},
        {"name": "name", "type": "string", "required": true, "nullable": false},
        {"name": "age", "type": "integer", "required": false, "min": 0, "max": 150},
        {"name": "created_at", "type": "datetime", "required": true}
    ],
    "unique_keys": ["id"],
    "strict": false
}
```

Supported types: `string`, `integer`, `float`, `boolean`, `date`, `datetime`

## Data Profiling Logic

The profiler generates statistical summaries for each column to support analyst exploration.

### How columns are classified

Each column produces a single profiling entry. The set of metrics shown for a column depends on how the column is classified: schema-defined numeric columns receive numeric statistics (mean, median, stdDev, min, max, IQR, outliers, etc.); non-numeric columns receive categorical metrics (unique counts, cardinality, duplicates, and value histograms).

**Classification rules:**

1.  **Schema precedence**: If the file’s pinned schema explicitly marks the column numeric (for example: `integer`, `bigint`, `float`, `numeric`, `decimal`), the profiler treats it as numeric.
2.  **Heuristic fallback**: When no schema type is provided, the profiler attempts to coerce non‑null values to numbers and classifies the column as numeric only when at least **80%** of non‑null values parse as numbers; otherwise it is treated as categorical.

**Example**: For a free‑text field like `first_name`, a single row with value `12345` will not turn the column numeric: if the schema marks `first_name` as string it stays categorical, and if there are many names with only one numeric-looking value the numeric coercion rate will be below 80%, so the column remains categorical.

## Database Tables

The pipeline reads/writes to these `reporting.*` tables:

| Table | Purpose |
|-------|---------|
| `monitoring_file` | Monitored file configurations |
| `monitoring_file_schema_definition` | Schema definitions for validation |
| `monitoring_file_run` | Hourly processing runs (unique by file+date+hour) |
| `monitoring_file_data_quality` | Quality scores, metrics, deductions |
| `monitoring_file_data_profile` | Profiling payloads (stats, distributions, samples) |
| `monitoring_file_failed_validation` | Rule-level failure details |

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `DB_HOST` | Database host | `localhost` |
| `DB_PORT` | Database port | `5432` |
| `DB_NAME` | Database name | `postgres` |
| `DB_USER` | Database user | `postgres` |
| `DB_PASSWORD` | Database password | - |
| `AWS_ACCESS_KEY_ID` | AWS access key (optional for IAM) | - |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key (optional for IAM) | - |
| `AWS_REGION` | AWS region | `us-gov-west-1` |
| `SQS_QUEUE_URL` | SQS Queue URL for `file-processing-sqs` consumer | - |
| `S3_SOURCE_BUCKET` | Source bucket for S3 operations | - |
| `S3_DESTINATION_BUCKET` | Destination bucket | - |

## Package-level .env and DB configuration

You can set package-local environment variables by creating `packages/file_processing/.env` (the CLI will load it automatically).

Use this file to configure local S3 shim and database connection settings used during development. There are two supported ways to configure the database:

1) Full DB URL (recommended):

```
DATABASE_URL=postgresql://user:password@hostname:5432/dbname
```

2) Individual DB_* variables:

```
DB_HOST=hostname
DB_PORT=5432
DB_NAME=etl
DB_USER=etl
DB_PASSWORD=secret
```

When the job runs, `etl_core.database.client.DatabaseClient` reads environment variables in the usual way; because the CLI loads the package `.env` before job discovery, the DB variables set in `packages/file_processing/.env` are available to `DatabaseClient`.

Tip: Commit `packages/file_processing/.env.example` to the repo and copy it to `.env` when you need to run locally (do not commit secrets).

## Local development vs Production

We run the exact same production code in both environments. For local development you can:

- Mimic incoming SQS/SNS events by passing an AWS-style event JSON to the job.
- Mock object downloads by setting `LOCAL_S3_ROOT` (the job will read objects from local disk in the same key layout as S3).
- Point the `DatabaseClient` at the shared Postgres (set `DATABASE_URL` or `DB_*` environment variables) — do not stand up a separate Postgres in compose for local dev unless you want a full local DB.

This keeps development and production behavior identical and reduces surprises when deploying.

### Event formats you can pass to `--event-json`

1) Direct simple payload

```json
{"bucket": "my-bucket", "key": "agency/demo/files/my-file/2026-01-04/12/data.csv"}
```

2) AWS S3 Event Records

```json
{"Records": [{"s3": {"bucket": {"name": "my-bucket"}, "object": {"key": "agency/demo/files/my-file/2026-01-04/12/data.csv"}}}]}
```

3) SNS-wrapped message (common when S3 -> SNS -> SQS -> consumer)

```json
{"Records": [{"Sns": {"Message": "{\"Records\": [{\"s3\": {\"bucket\": {\"name\": \"my-bucket\"}, \"object\": {\"key\": \"agency/demo/files/my-file/2026-01-04/12/data.csv\"}}]}"}}]}
```

4) SQS-wrapped message (SQS consumer with SNS/S3 payload in body)

```json
{"Records": [{"body": "{\"Records\": [{\"s3\": {\"bucket\": {\"name\": \"my-bucket\"}, \"object\": {\"key\": \"agency/demo/files/my-file/2026-01-04/12/data.csv\"}}]}"}]}
```

### Local file shim (simulate S3 object bytes)

1. Set `LOCAL_S3_ROOT` to a directory where you place files that map to S3 keys.

Example directory layout for the key `agency/demo/files/my-file/2026-01-04/12/data.csv`:

```
$LOCAL_S3_ROOT/agency/demo/files/my-file/2026-01-04/12/data.csv
```

2. Set `LOCAL_S3_ROOT` and run the job with an AWS-style event (see examples above):

```bash
export LOCAL_S3_ROOT=/path/to/local/s3/root
file-processing run s3_data_quality_job -- \
  --event-json '{"Records":[{"s3":{"bucket":{"name":"ignored-local"},"object":{"key":"agency/demo/files/my-file/2026-01-04/12/data.csv"}}}]}'
```

The job will use the same download/parse/validate/persist code paths as production; only the S3 client is swapped for a tiny filesystem-backed shim.

### Production usage

- In production the job receives SQS/SNS messages with S3 records and runs the same `s3_data_quality_job` entrypoint.
- Configure AWS credentials (IAM) and `S3Config` via environment variables to let the `S3Client` use real S3.
- Configure `DatabaseClient` via `DATABASE_URL` or `DB_*` environment variables to point at the shared platform Postgres.

### Quick tips

- To replay events for debugging, save the original event JSON and pass it with `--events-file`.
- For tests and local CI, inject test doubles for `DatabaseClient`, `MonitoringRepository`, and `S3Client` into the `entrypoint` call (the job supports DI).

## Testing

```bash
# Run unit tests
python -m pytest packages/file_processing/tests/unit -v

# Run a single test file
python -m pytest packages/file_processing/tests/unit/test_s3_data_quality_processor.py -q
```

## Development

### Adding a New Validator

1. Create a new validator in `validators/`:

```python
from file_processing.validators.base import BaseValidator, ValidationResult

class MyValidator(BaseValidator):
    @property
    def validator_name(self) -> str:
        return "my_check"

    def validate(self, rows, columns, schema_definition) -> ValidationResult:
        # Validation logic
        return ValidationResult(passed=True, details="OK")
```

2. Register in the processor's `_run_validations()` method.

### Adding a New Parser

1. Create a new parser in `parsers/`:

```python
from file_processing.parsers.base import BaseParser, ParseResult

class MyParser(BaseParser):
    @property
    def format_name(self) -> str:
        return "myformat"

    def parse(self, file_obj) -> ParseResult:
        # Parsing logic
        return ParseResult(success=True, rows=[], columns=[])
```

2. Register in `parsers/registry.py`.
