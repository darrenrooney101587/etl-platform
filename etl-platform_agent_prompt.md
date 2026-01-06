# etl-platform Agent Prompt: Data Quality Processing Pipeline

Purpose
- This prompt is intended to be copied into the `etl-platform` repository (or given to an agent working there). It instructs backend engineers/agents to implement the processing pipeline that reads S3 objects, computes data quality and profiling, and writes results into a shared Postgres database.

Important context
- The etl-platform service does NOT have access to other application repositories. It interacts directly with:
  - S3 (or S3-compatible store)
  - the shared Postgres database (schema described below)
- Avoid referencing any artifacts from other repos.

Constraints
- Python 3.10
- Config via environment variables
- Use dependency injection for S3 and DB clients so the code is testable and mockable
- Do not store secrets in code

Primary responsibilities
1. Listen for S3 object-created notifications (SQS/EventBridge/webhook/batch input)
2. Resolve which monitoring configuration the object corresponds to
3. Create or upsert an idempotent MonitoringFileRun
4. Download and parse the object (CSV/JSON/Parquet supported)
5. Compute data quality checks, deductions, score, and profiling payloads
6. Persist the results into the `reporting.*` tables described below
7. Emit structured logs and observability metrics

DB table mirrors
- Implement local ORM or SQL models that match the following table definitions exactly (these exist in the shared DB):

1) monitoring_file_schema_definition
- id (serial)
- name (varchar)
- description (text)
- definition (jsonb)
- created_at, updated_at

2) monitoring_file
- id
- file_name
- agency_slug
- latest_data_quality_score (nullable int)
- schema_definition_id (nullable FK to monitoring_file_schema_definition)

3) monitoring_file_run
- id
- monitoring_file_id (FK to monitoring_file)
- agency_id (nullable int)
- created_at, updated_at
- file_last_modified (timestamp)
- file_range_lower_limit (timestamp nullable)
- file_size (bigint)
- run_date (date)
- run_hour (int)

Uniqueness: (monitoring_file_id, run_date, run_hour) unique.

4) monitoring_file_data_quality
- id
- monitoring_file_run_id (one-to-one to monitoring_file_run)
- score (int)
- passed (boolean)
- metrics (jsonb)
- deductions (jsonb)
- failed_validation_message (text nullable)
- failed_validation_rules (jsonb nullable)
- created_at, updated_at

5) Optional: monitoring_file_failed_validation
- optional table for rule-level failure rows if you need to persist expand failure details

6) Optional: monitoring_file_data_profile
- monitoring_file_run_id (one-to-one)
- profile_payload (jsonb)
- created_at, updated_at

JSON contracts
- MonitoringFileDataQuality.metrics must include keys: schemaValidation, formatParsing, completeness, boundsRange, uniqueness; each key is an object with at least `passed: bool` and `details: string`.
- MonitoringFileDataQuality.deductions must include numeric keys: schema, format, completeness, bounds, uniqueness. Use numeric values (can be fractional).
- MonitoringFileDataProfile.profile_payload should include: statisticalSummary, completenessOverview, typeFormatIssues, uniquenessOverview, valueDistributions, boundsAnomalies, and optional sampleData (columns[] and rows[]). Cap sample rows at 25–50 and distribution examples to 10–25 items.

Scoring rules (implement in backend)
- Starting score: 100
- Deductions: schema 40, format 35, completeness 20, bounds 15, uniqueness 10
- Deductions may be proportional (partial failures). Example: if 1 of 5 schema fields failed, deduct 40 * 1/5 = 8.
- Final score = clamp(round(100 - sum(deductions)), 0, 100)
- passed = score >= 80

Processing flow
1. Receive event with {bucket, key, optional object metadata}
2. Parse key to determine agency_slug, file_name, and time window (run_date, run_hour). Prefer object last_modified if available.
3. Query monitoring_file by (agency_slug, file_name). If not found, log and either create a placeholder monitoring_file (if allowed) or return a warning/error per config.
4. Upsert/find monitoring_file_run using (monitoring_file_id, run_date, run_hour). Use transactions/locks to ensure idempotency.
5. Download object and parse (streamed parsing where possible). Supported formats: CSV (utf-8, with header), JSONL, Parquet. Implement a pluggable parser registry.
6. If parse fails, write a data_quality row with formatParsing.passed=false and deduction for `format` (35) and include the parser error in `failed_validation_message`.
7. Run checks:
   - Schema validation: compare type/required fields against `MonitoringFileSchemaDefinition.definition` if present
   - Completeness: required fields non-null count and percent
   - Uniqueness: for declared unique key(s), compute unique ratio
   - Bounds: numeric/date ranges for declared bounds in schema definition
8. Compute deductions proportionally and populate `metrics` and `deductions` JSON
9. Compute `score` and `passed`
10. Generate a profiling payload (stat summary, distributions, sample rows capped)
11. Persist `monitoring_file_data_quality` (upsert), optional `monitoring_file_failed_validation` rows, and optional `monitoring_file_data_profile`
12. Update `monitoring_file.latest_data_quality_score` with this run's score (or compute a rolling aggregate per config)

Idempotency and upserts
- Use SELECT ... FOR UPDATE or advisory locks by (monitoring_file_id, run_date, run_hour) during run creation and quality write to avoid duplicates.
- `monitoring_file_run` should be unique by (monitoring_file_id, run_date, run_hour) — if a row exists, re-use it and update file_last_modified/file_size as needed.
- `monitoring_file_data_quality` is one-to-one to a run. Upsert behavior: INSERT ... ON CONFLICT(monitoring_file_run_id) DO UPDATE SET ...

Error handling and observability
- Use structured logs (JSON) with fields: level, ts, bucket, key, monitoring_file_id, monitoring_file_run_id, error
- Persist human-readable failure messages in `failed_validation_message` and machine-friendly details in `failed_validation_rules` (JSON)
- Emit metrics for processed files, failed parses, scoring distribution, and processing latency

Testing and local development
- Provide a small test harness that can replay S3 events from a JSON file for local testing
- Tests should include:
  - parser unit tests for supported formats
  - scoring/deduction unit tests (happy + partial failure cases)
  - integration test using a test Postgres instance (docker compose) and local S3 (minio/localstack)

Configuration
- Read configuration from environment variables or a config file:
  - DATABASE_URL
  - S3_ENDPOINT (optional)
  - S3_REGION
  - S3_ACCESS_KEY, S3_SECRET_KEY (CI/test only; prod uses IAM)
  - POLL_QUEUE_URL / SQS settings (or EventBridge endpoint)
  - LOG_LEVEL

Deliverable checklist for the etl-platform implementer
- [ ] Python service skeleton with DI for S3 and DB
- [ ] Mirror models (ORM or SQL) for the reporting.* tables
- [ ] Parser registry supporting CSV/JSONL/Parquet
- [ ] Schema validator that consumes the `definition` JSON from the schema table
- [ ] Deduction and scoring implementation (with unit tests)
- [ ] Profiling payload generator, capped as described
- [ ] Upsert logic for runs and quality rows (idempotent)
- [ ] README with run instructions and env var examples

If you need to coordinate with the DB owner: ensure the `monitoring_file_data_profile` table exists before attempting to write profiling payloads.

Example S3 event (input to pipeline)
```json
{
  "bucket": "my-bucket",
  "key": "agency/tenant-a/files/file-name/2026-01-04/12/data.csv",
  "last_modified": "2026-01-04T12:34:56Z",
  "size": 12345
}
```

Example metrics/deductions output (to write to `monitoring_file_data_quality`)
```json
{
  "score": 77,
  "passed": false,
  "metrics": {
    "schemaValidation": {"passed": true, "details": "All required columns present"},
    "formatParsing": {"passed": true, "details": "CSV parsed (header)"},
    "completeness": {"passed": false, "details": "3% of rows have nulls in required fields"},
    "boundsRange": {"passed": true, "details": "All values in expected ranges"},
    "uniqueness": {"passed": false, "details": "Primary key uniqueness 97%"}
  },
  "deductions": {"schema": 0, "format": 0, "completeness": 6, "bounds": 0, "uniqueness": 17}
}
```

Notes
- Keep payloads rightsized for storage and UI consumption. The frontend expects profiling and sample rows but payload size should be bounded.
- Where the schema definition exists, prefer strict validation and informative failure messages that the frontend can display.
- When in doubt about creating monitoring_file rows automatically, make behavior configurable (auto-create vs strict lookup-only).

Good luck — the frontend and webserver teams will rely on your outputs to power the data quality UI.
