# reporting_seeder schema contract

DDL lives in `etl-database-schema`. This file captures the required tables/materialized views derived from Django manifests and frontend expectations (`mockSeederData.ts`, `mockSeederHistory.ts`).

## Existing inputs (manifests)
- `reporting.seeder_custom_report_manifest`
  - `id`, `table_name`, `report_name`, `agency_id`, `agency_slug`, `query`, `database_id`, `enabled`
- `reporting.seeder_canned_report_manifest`
  - `id`, `agency_id`, `agency_slug`, `canned_report_id`
- `reporting.seeder_canned_report`
  - `id`, `table_name`, `report_name`, `query`, `database_id`

## New/updated objects

### 1) reporting.seeder_run_history (new table)
Tracks per-manifest run history for dashboard + troubleshooting.

Columns (proposed):
- `id` bigserial primary key
- `run_id` text not null
- `manifest_id` integer not null -- FK to seeder manifests or canned manifests
- `table_name` text not null
- `report_name` text not null
- `agency_id` integer not null
- `agency_slug` text not null
- `report_type` text not null -- enum-ish: 'custom' | 'canned'
- `status` text not null -- 'pending' | 'running' | 'success' | 'error'
- `start_time` timestamptz not null default now()
- `finish_time` timestamptz
- `duration_seconds` integer
- `records_processed` bigint default 0
- `bytes_processed` bigint default 0
- `memory_usage_mb` integer
- `cpu_percentage` integer
- `consecutive_failures` integer default 0 -- see dashboard trending flags
- `errors` text
- `created_at` timestamptz not null default now()
- `updated_at` timestamptz not null default now()

Indexes:
- btree on (table_name)
- btree on (agency_slug)
- btree on (start_time desc)

### 2) reporting.seeder_job_status (new table)
Holds the latest status per manifest to power the seederMonitoring list (with consecutive failure and long-running flags).

Columns (proposed):
- `table_name` text primary key  -- using table_name since manifest_id might collide
- `manifest_id` integer not null
- `report_name` text not null
- `report_type` text not null
- `agency_id` integer not null
- `agency_slug` text not null
- `status` text not null -- 'pending' | 'running' | 'success' | 'error'
- `duration_seconds` integer default 0
- `start_time` timestamptz
- `consecutive_failures` integer default 0
- `last_run_id` text
- `last_errors` text
- `updated_at` timestamptz not null default now()

Indexes:
- primary key (table_name)
- btree on (agency_slug)

### 3) Materialized views (per manifest)
- One matview per manifest using the manifest `table_name`. Creation/refresh handled by reporting_seeder. No drop-on-next-iteration semantics; views are created once and refreshed.

### 4) Update logic
- `reporting_seeder` package explicitly maintains `seeder_job_status` via upserts in `HistoryRepository`. No schema-level triggers are required for basic status tracking.

## Frontend field mapping
- `mockSeederData.ts` expectations per job row:
  - id -> `manifest_id` (or table_name), reportName -> report_name, tableName -> table_name, reportType -> report_type, status -> status, durationSeconds -> duration_seconds, startTime -> start_time, consecutiveFailures -> consecutive_failures, agencyId -> agency_id, agencyName -> (join from Agency if needed), agencySlug -> agency_slug
- `mockSeederHistory.ts` expectations per history row:
  - runId -> run_id, status -> status, startTime -> start_time, finishTime -> finish_time, durationSeconds -> duration_seconds, recordsProcessed -> records_processed, bytesProcessed -> bytes_processed, memoryUsageMb -> memory_usage_mb, cpuPercentage -> cpu_percentage, errors -> errors

## Next steps for etl-database-schema agent
- Add tables `reporting.seeder_run_history` and `reporting.seeder_job_status` with columns above.
- Ensure FK relationships to manifest tables or agency table as appropriate.
- Consider triggers to maintain `seeder_job_status` on insert/update of `seeder_run_history` (or let application update both).
- Add indexes noted above.
- Optional: create helper view `reporting.seeder_dashboard` for frontend consumption.
