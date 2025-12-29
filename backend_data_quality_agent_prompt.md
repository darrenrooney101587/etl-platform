# Backend Agent Prompt: Data Quality Pipeline Implementation (ETL Repo)

## Role
You are a Senior Backend Engineer specializing in Python, Django, and Data Engineering.

## Objective
Build the backend infrastructure to ingest files from S3, validate them against defined schemas, calculate data quality metrics, and persist the results.
**Crucial Context**: You are working in a **new, separate repository** called `etl-file-monitoring`. This repository is responsible for data processing only. It connects to the same PostgreSQL database as the main web application (`bms-admin`), but does not share code with it.

## Inputs

### 1. Data Quality Metrics & Deductions
(Reference from `DATA_QUALITY_METRICS.md`)
*   **Base Score**: 100
*   **Deductions**:
    *   **Schema Validation**: -40 pts (Structure/columns mismatch)
    *   **Format Parsing**: -35 pts (Invalid file format/corrupt)
    *   **Completeness**: -20 pts (Nulls in required fields)
    *   **Bounds & Range**: -15 pts (Values out of expected range)
    *   **Uniqueness**: -10 pts (Duplicate primary keys)

### 2. Reference Data Models (from `bms-admin`)
Since you cannot access the `bms-admin` codebase, use these model definitions to create your local mirrors (you can set `managed = False` if you don't want to manage migrations, or just replicate them to interact with the DB).

```python
class MonitoringFile(models.Model):
    id = models.AutoField(primary_key=True)
    s3_url = models.CharField(max_length=250, blank=True)
    file_name = models.CharField(max_length=250, blank=False)
    range = models.CharField(max_length=20, blank=False)
    is_active = models.BooleanField(default=False, blank=True)
    agency = models.ForeignKey('Agency', models.PROTECT, null=True) # You'll need an Agency stub too
    agency_slug = models.CharField(max_length=255, null=False)
    notify_slack = models.BooleanField(default=False)
    is_missing = models.BooleanField(default=False)
    latest_data_quality_score = models.IntegerField(null=True, blank=True)
    # NEW FIELD TO ADD/EXPECT:
    # schema_definition = models.ForeignKey('MonitoringFileSchemaDefinition', on_delete=models.SET_NULL, null=True)

    class Meta:
        managed = False # Managed by bms-admin
        db_table = '"reporting"."monitoring_file"'

class MonitoringFileSchemaDefinition(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, blank=False, unique=True)
    description = models.TextField(blank=True, null=True)
    definition = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file_schema_definition"'

class MonitoringFileRun(models.Model):
    id = models.AutoField(primary_key=True)
    monitoring_file = models.ForeignKey(MonitoringFile, on_delete=models.CASCADE, related_name='monitoring_file_runs', db_column='monitoring_file_id')
    created_at = models.DateTimeField(auto_now_add=True)
    file_size = models.BigIntegerField(blank=True)
    run_date = models.DateField(blank=True)
    run_hour = models.IntegerField(blank=False)
    
    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file_run"'

class MonitoringFileDataQuality(models.Model):
    id = models.AutoField(primary_key=True)
    monitoring_file_run = models.OneToOneField(MonitoringFileRun, on_delete=models.CASCADE, related_name='data_quality', db_column='monitoring_file_run_id')
    score = models.IntegerField()
    passed = models.BooleanField(default=False)
    metrics = models.JSONField(default=dict)
    deductions = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file_data_quality"'
```

## Tasks

### 1. Setup `etl-file-monitoring` Project
*   Initialize a Python/Django project structure.
*   Configure database connection to the shared PostgreSQL instance.
*   **Model Replication**: Create `models.py` containing the `MonitoringFile`, `MonitoringFileRun`, `MonitoringFileDataQuality`, and `MonitoringFileSchemaDefinition` models as defined above.
    *   All models should have `managed = False` and use the correct `db_table` names.
*   **No migrations should be created in this repo**; all schema changes are managed in `bms-admin`.

### 2. Ingestion Logic (Service Layer)
Create a service (e.g., `services/ingestion.py`) to handle file processing:
*   **`process_s3_file(bucket, key)`**:
    1.  **Download**: Fetch file from S3.
    2.  **Preprocessing**: Convert Excel to CSV if needed.
    3.  **Schema Resolution**:
        *   Query `MonitoringFile` by filename/agency.
        *   Check if `monitoring_file.schema_definition` is set.
    4.  **Validation & Scoring Algorithms**:
        *   Load data (recommend using `pandas`).
        *   **Format Parsing (-35 pts)**: Try to parse the file. If it fails (e.g., `ParserError`), apply deduction and **stop** further validation.
        *   **Schema Validation (-40 pts)**: Compare file columns against `SchemaDefinition`.
            *   *Fail condition*: Missing required columns or extra columns (if strict).
            *   *Action*: Apply deduction. If missing columns prevent further checks, stop.
        *   **Completeness (-20 pts)**: Check for nulls/NaNs in columns marked `required=True` in schema.
            *   *Fail condition*: Any row has a null in a required column.
        *   **Uniqueness (-10 pts)**: Check columns marked `unique=True`.
            *   *Fail condition*: `df[col].is_unique` is False.
        *   **Bounds & Range (-15 pts)**: Check columns with defined ranges (e.g., `min`, `max`).
            *   *Fail condition*: Any value falls outside the range.
    5.  **Scoring Calculation**:
        *   Start with **100**.
        *   Subtract points for each failed category above.
        *   Score cannot go below 0.
        *   `passed` boolean is True if Score >= 80.
    6.  **Persistence**: Write `MonitoringFileRun` and `MonitoringFileDataQuality` records to the DB.

### 3. SQS Integration & Local Testing
*   **Production Mode**: Create a worker (e.g., management command) that polls the SQS queue for S3 `ObjectCreated` events.
*   **Local/Dev Mode**: We need a way to trigger ingestion locally without a real SQS queue.
    *   Implement a **REST API endpoint** (e.g., `/api/trigger-ingestion/`) OR a **Management Command** (e.g., `process_file --bucket X --key Y`) that mimics the SQS event payload.
    *   This allows developers to "push" a file event to the running service.
*   **Docker**:
    *   Create a `Dockerfile` for the `etl-file-monitoring` application.
    *   It should be ready for deployment to EKS (stateless, configurable via env vars).

## Constraints
*   **Shared Database**: Write to the existing tables.
*   **Python 3.10**.
*   **Error Handling**: Robust logging.
*   **Environment Variables**: All configuration (DB credentials, SQS queue, etc.) must be loaded from a `.env` file using a standard loader (e.g., `python-dotenv`). The agent must document and enforce this pattern for local/dev and production.

## Deliverables
1.  `etl-file-monitoring` codebase structure.
2.  `models.py` with replicated models.
3.  `services/ingestion.py` with validation logic.
4.  `management/commands/run_worker.py` for SQS polling.
5.  `Dockerfile` and local trigger mechanism.
6.  `.env.example` and documentation for all required environment variables.
