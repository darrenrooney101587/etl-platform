# File Monitoring — Data Quality Feature Specification

## Status Update
- **Frontend API**: Defined below.
- **Mock Data**: Migrated to database. Seed data now populates `MonitoringFileDataQuality` tables.
- **Next Steps**: Build the actual backend ingestion and processing pipeline to populate these tables with real data from S3.

# Backend Ingestion & Processing (New Work)

## Goal
Implement the backend pipeline to ingest files from S3, validate them against defined schemas, calculate data quality metrics, and store results in the database.

## Workflow
1.  **Trigger**: Agency drops a file in S3.
2.  **Event**: S3 event triggers an SQS/SNS notification (existing infrastructure).
3.  **Ingestion**: Backend subscribes to the queue and picks up the file event.
4.  **Preprocessing**:
    *   If Excel (single sheet): Convert to CSV.
    *   If CSV: Process directly.
5.  **Schema Resolution**:
    *   Identify the `MonitoringFile` record for this file (using existing lookup logic based on filename/agency).
    *   Check if the `MonitoringFile` has a manually assigned `SchemaDefinition`.
    *   If no schema is assigned, skip detailed validation (or run only generic checks) and log that schema assignment is pending.
6.  **Validation & Scoring**:
    *   Run checks defined in `frontend/docs/DATA_QUALITY_METRICS.md`.
    *   **Schema Validation**: Compare against `SchemaDefinition` (columns, types).
    *   **Bounds & Range**: Check values against constraints in `SchemaDefinition`.
    *   **Uniqueness**: Check primary keys defined in `SchemaDefinition`.
    *   **Completeness**: Check for nulls in required columns.
    *   **Format**: Check CSV parsing health.
7.  **Persistence**:
    *   Create `MonitoringFileRun`.
    *   Calculate Score & Deductions.
    *   Create `MonitoringFileDataQuality` record.

## Architecture Constraints
- **Repository Split**:
    - **`bms-admin`**: Remains the web server for frontend presentation, database management, and configuration (UI).
    - **`etl-file-monitoring`**: A new repository dedicated to the backend ingestion and data processing pipeline.
- **Database**: Both repositories connect to the same PostgreSQL database. `bms-admin` manages the models/migrations; `etl-file-monitoring` reads/writes to these tables.
- **No new AWS Lambdas**: Process the SQS messages within the `etl-file-monitoring` application (e.g., via a worker process).
- **Data Models**:
    - Define `SchemaDefinition` and update `MonitoringFile` in `bms-admin` (so they are manageable via Django Admin/UI).
    - `etl-file-monitoring` must replicate or import these model definitions to interact with the DB.

## Reference
- Metric Definitions: `frontend/docs/DATA_QUALITY_METRICS.md`
- Existing Models: `bms_reporting/models.py` (`MonitoringFile`, `MonitoringFileRun`, `MonitoringFileDataQuality`)
