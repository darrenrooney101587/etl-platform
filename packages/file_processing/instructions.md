# Backend Agent Prompt: Data Quality Processing Pipeline (etl-platform)

## Role
You are a Senior Backend/Data Engineer building the backend processing components that feed the shared Postgres database used by multiple services (a Django web app and a React frontend). You do not have access to those other repositories; you only have database access and S3 event sources.

## Objective
Build backend processes in the etl-platform that:
1) consume S3 object-created notifications (bucket + key),
2) download and parse files (CSV/JSON/Parquet as configured),
3) compute data quality validation and profiling outputs,
4) write/merge results into an existing shared PostgreSQL database so that the frontend/webserver can render data quality dashboards.

### Important constraints
- etl-platform does NOT have access to the Django/React repos — it only interacts with the shared Postgres database and S3.
- The database tables described in this document already exist in the shared DB.
- etl-platform must not rely on application code from other repos; instead implement local mirror models (Django models, SQLAlchemy models, or raw SQL) matching the shared tables.

etl-platform’s scope:
- Ingest S3 notifications and objects
- Compute data quality metrics, deductions, and profile payloads
- Persist results into `reporting.*` tables according to the contracts below

What etl-platform is NOT responsible for:
- Rendering UI or serving frontend requests
- Acknowledgment workflows or manual overrides stored by the web UI (those columns exist but are not managed here)

## High-level plan / deliverables
- A small, testable Python service (Python 3.10) or equivalent that:
  - Listens for S3 object-created events (SQS/EventBridge, or a batch replay runner for backfills)
  - Resolves which monitoring file configuration the object belongs to
  - Creates or upserts a MonitoringFileRun (idempotent by monitoring_file, run_date, run_hour)
  - Downloads and parses the file with streaming where feasible
  - Runs schema/format/completeness/uniqueness/bounds checks
  - Computes deductions and final score (0–100) per contract and marks passed/failed
  - Writes/updates rows in `reporting.monitoring_file_run`, `reporting.monitoring_file_data_quality`, optionally `reporting.monitoring_file_failed_validation` and `reporting.monitoring_file_data_profile`
  - Updates `reporting.monitoring_file.latest_data_quality_score`
- Unit tests for core logic (parsing, scoring, deduction calculation), and integration tests that run against a test Postgres instance and a local S3-compatible store (minio/localstack)
- README with configuration (env vars), run instructions, and example S3 events

Acceptance criteria
- Given an S3 event the pipeline writes the expected `monitoring_file_run` and corresponding `monitoring_file_data_quality` row with correct deductions and metrics JSON
- Idempotent: reprocessing the same S3 object/run does not create duplicate runs or duplicate quality rows
- Profiling payload size limits enforced (sample rows capped, distributions capped)

## Data quality scoring contract (backend MUST compute)
- Start score at 100 and subtract fixed points when a category fails (or partially fails — see partial deduction guidance below):
  - schema: 40
  - format: 35
  - completeness: 20
  - bounds: 15
  - uniqueness: 10
- Score is clamped to `[0, 100]` and rounded to an integer.
- Pass/fail rule: `passed = (score >= 80)`

Partial deductions
- Deductions may be fractional or proportional when only a subset of checks within a category fails. For example, if schema has 5 fields and one field fails but others pass, you may deduct (40 * 1/5) = 8 points. Record the exact numeric deductions in `deductions` JSON.

Example deduction JSON (MonitoringFileDataQuality.deductions):
{
  "schema": 8,
  "format": 35,
  "completeness": 5,
  "bounds": 0,
  "uniqueness": 10
}

Final score = max(0, 100 - sum(deductions.values()))

## Shared database contract (Django model mirrors)
Create local mirror model definitions (or equivalent SQL definitions) to read/write the shared DB. The following reference Django models reflect the tables and columns the pipeline must write to.

### 1) MonitoringFileSchemaDefinition
```python
"""Django model mirror for reporting.monitoring_file_schema_definition."""

from __future__ import annotations

from django.db import models


class MonitoringFileSchemaDefinition(models.Model):
    """Schema definition used to validate monitoring files."""

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    definition = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file_schema_definition"'
```

### 2) MonitoringFile
```python
"""Django model mirror for reporting.monitoring_file."""

from __future__ import annotations

from django.db import models


class MonitoringFile(models.Model):
    """Monitored file configuration and data quality cache."""

    id = models.AutoField(primary_key=True)
    file_name = models.CharField(max_length=250)
    agency_slug = models.CharField(max_length=255)

    latest_data_quality_score = models.IntegerField(null=True, blank=True)

    schema_definition = models.ForeignKey(
        MonitoringFileSchemaDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='schema_definition_id',
        related_name='+',
    )

    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file"'
```

### 3) MonitoringFileRun
```python
"""Django model mirror for reporting.monitoring_file_run."""

from __future__ import annotations

from django.db import models


class MonitoringFileRun(models.Model):
    """A single hourly (run_date, run_hour) processing run for a monitoring file."""

    id = models.AutoField(primary_key=True)
    monitoring_file = models.ForeignKey(
        MonitoringFile,
        on_delete=models.CASCADE,
        db_column='monitoring_file_id',
        related_name='+',
    )

    agency_id = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    file_last_modified = models.DateTimeField(null=True, blank=True)
    file_range_lower_limit = models.DateTimeField(null=True, blank=True)
    file_size = models.BigIntegerField(blank=True)

    run_date = models.DateField(blank=True)
    run_hour = models.IntegerField()

    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file_run"'
```

Uniqueness:
- `(monitoring_file_id, run_date, run_hour)` is unique in the database.

### 4) MonitoringFileDataQuality
```python
"""Django model mirror for reporting.monitoring_file_data_quality."""

from __future__ import annotations

from django.db import models


class MonitoringFileDataQuality(models.Model):
    """Computed data quality score and dimension breakdown for a run."""

    id = models.AutoField(primary_key=True)
    monitoring_file_run = models.OneToOneField(
        MonitoringFileRun,
        on_delete=models.CASCADE,
        db_column='monitoring_file_run_id',
        related_name='+',
    )

    score = models.IntegerField()
    passed = models.BooleanField(default=False)

    metrics = models.JSONField(default=dict)
    deductions = models.JSONField(default=dict)

    failed_validation_message = models.TextField(null=True, blank=True)
    failed_validation_rules = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # The following columns are managed by the web app acknowledgment workflow (do not set here):
    # acknowledgment_status, acknowledged_by_id, acknowledged_by_username, acknowledged_at, acknowledgment_notes

    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file_data_quality"'
```

### 5) Optional: MonitoringFileFailedValidation
```python
"""Django model mirror for reporting.monitoring_file_failed_validation."""

from __future__ import annotations

from django.db import models


class MonitoringFileFailedValidation(models.Model):
    """Rule-level failure details for a run (optional if used by UI/backoffice)."""

    id = models.AutoField(primary_key=True)

    monitoring_file = models.ForeignKey(
        MonitoringFile,
        on_delete=models.CASCADE,
        db_column='monitoring_file_id',
        related_name='+',
    )

    monitoring_file_run = models.OneToOneField(
        MonitoringFileRun,
        on_delete=models.CASCADE,
        db_column='monitoring_file_run_id',
        related_name='+',
    )

    rule_name = models.CharField(max_length=250, blank=True)
    rule_type = models.CharField(max_length=250, blank=True)
    rule_path = models.CharField(max_length=250, blank=True)
    validated_field_names = models.CharField(max_length=250, blank=True)
    validated_values = models.CharField(max_length=250, blank=True)
    rule_parameters = models.CharField(max_length=250, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_message = models.CharField(max_length=250, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file_failed_validation"'
```

### 6) Recommended: MonitoringFileDataProfile (profiling + sampling)
```python
"""Django model mirror for reporting.monitoring_file_data_profile."""

from __future__ import annotations

from django.db import models


class MonitoringFileDataProfile(models.Model):
    """Data profiling payload used for analyst exploration (stats, distributions, samples)."""

    id = models.AutoField(primary_key=True)
    monitoring_file_run = models.OneToOneField(
        MonitoringFileRun,
        on_delete=models.CASCADE,
        db_column='monitoring_file_run_id',
        related_name='+',
    )

    profile_payload = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file_data_profile"'
```

If this profiling table does not exist in the shared DB yet, coordinate with the DB owner.

## JSON payload contracts (what to write)

### 1) Quality metrics JSON (`MonitoringFileDataQuality.metrics`)
Write a stable structure with the keys below:

- `schemaValidation`: `{passed: bool, details: str, ...optionalMetadata}`
- `formatParsing`: `{passed: bool, details: str, ...optionalMetadata}`
- `completeness`: `{passed: bool, details: str, ...optionalMetadata}`
- `boundsRange`: `{passed: bool, details: str, ...optionalMetadata}`
- `uniqueness`: `{passed: bool, details: str, ...optionalMetadata}`

### 2) Deductions JSON (`MonitoringFileDataQuality.deductions`)
Numeric keys:
- `schema`, `format`, `completeness`, `bounds`, `uniqueness`

### 3) Profiling JSON (`MonitoringFileDataProfile.profile_payload`)
Populate these keys (cap list sizes to keep payload small):
- `statisticalSummary`
- `completenessOverview`
- `typeFormatIssues`
- `uniquenessOverview`
- `valueDistributions`
- `boundsAnomalies`
- optional: `sampleData: {columns: string[], rows: any[][]}`

Payload limits:
- sample rows: 25–50
- outlier values / distribution buckets / anomaly examples: cap to reasonable sizes (10–25)

## Processing pipeline requirements

### Contract
Given an S3 object-created event
- `bucket: str`
- `key: str`

The pipeline must:
- locate the correct `MonitoringFile`
- create or reuse the correct `MonitoringFileRun` (idempotent)
- compute quality + profile outputs
- persist results

### Required steps
1) Receive the notification (SQS/EventBridge/etc.)
2) Resolve identifiers from the S3 key
   - determine `agency_slug`
   - determine `file_name`
   - determine `run_date` and `run_hour` (prefer S3 event time or object last_modified)
3) Query `reporting.monitoring_file` by `(agency_slug, file_name)`
4) Upsert/find `reporting.monitoring_file_run` using `(monitoring_file_id, run_date, run_hour)`
5) Download object from S3
6) Parse
   - if parse fails: mark `formatParsing.passed = false`, apply `format` deduction, stop
7) Validate
   - schema validation (if schema_definition exists)
   - completeness for required fields
   - uniqueness for unique fields
   - bounds/range for bounded fields
8) Compute score + passed
9) Compute profiling + sample rows
10) Persist
   - upsert `monitoring_file_data_quality` for the run
   - write `monitoring_file_data_profile` if available
   - update `monitoring_file.latest_data_quality_score`

## Observability
- Structured logs including:
  - bucket/key
  - monitoring_file_id
  - monitoring_file_run_id
- Store failure context in `failed_validation_message` / `failed_validation_rules`.

## Constraints
- Python 3.10
- Exceptions (no silent return codes)
- Dependency injection for external resources (S3 client, DB connection)
- Configuration via environment variables
- No secrets in code
