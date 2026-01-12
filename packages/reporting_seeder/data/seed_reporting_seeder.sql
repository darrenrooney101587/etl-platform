-- Seed data for reporting_seeder (development/dev-local only)
-- Adjust IDs and columns to match your schema; this file uses conservative columns from SCHEMA.md

-- Ensure test agency exists (may need additional columns in your real Agency table)
INSERT INTO public.agency (id, name)
VALUES (1, 'Test Agency')
ON CONFLICT (id) DO NOTHING;

-- Canned report (template)
INSERT INTO reporting.seeder_canned_report (id, table_name, report_name, query, database_id, module)
VALUES
  (100, 'reporting.canned_sales', 'Canned Sales', 'SELECT 1 AS placeholder LIMIT 0', 1, 1)
ON CONFLICT (id) DO NOTHING;

-- Map canned report to agency (manifest)
INSERT INTO reporting.seeder_canned_report_manifest (id, agency_id, agency_slug, canned_report_id)
VALUES
  (200, 1, 'test-agency', 100)
ON CONFLICT (id) DO NOTHING;

-- Custom report manifest (an example custom manifest referencing a proprietary query)
INSERT INTO reporting.seeder_custom_report_manifest (
  id, table_name, report_name, agency_id, agency_slug, query, database_id, enabled, module
)
VALUES
  (300, 'reporting.custom_demo', 'Custom Demo', 1, 'test-agency', 'SELECT 1 AS placeholder', 1, TRUE, 1)
ON CONFLICT (id) DO NOTHING;

-- Create example job status rows (dashboard current state)
INSERT INTO reporting.seeder_job_status (
  table_name, manifest_id, report_name, report_type, agency_id, agency_slug, status, duration_seconds, start_time, consecutive_failures, last_run_id, last_errors, updated_at
)
VALUES
  ('reporting.canned_sales', 100, 'Canned Sales', 'canned', 1, 'test-agency', 'success', 0, now(), 0, NULL, NULL, now()),
  ('reporting.custom_demo', 300, 'Custom Demo', 'custom', 1, 'test-agency', 'success', 0, now(), 0, NULL, NULL, now())
ON CONFLICT (table_name) DO UPDATE SET updated_at = now();

-- Insert a couple of recent run history rows to populate the UI history list
INSERT INTO reporting.seeder_run_history (
  run_id, manifest_id, table_name, report_name, agency_id, agency_slug, report_type, status, start_time, finish_time, duration_seconds, records_processed, bytes_processed, memory_usage_mb, cpu_percentage, consecutive_failures, errors, created_at, updated_at
)
VALUES
  ('seed-run-1', 100, 'reporting.canned_sales', 'Canned Sales', 1, 'test-agency', 'canned', 'success', now() - interval '5 minutes', now() - interval '5 minutes' + interval '10 seconds', 10, 0, 0, 5, 2, 0, NULL, now() - interval '5 minutes', now() - interval '5 minutes'),
  ('seed-run-2', 300, 'reporting.custom_demo', 'Custom Demo', 1, 'test-agency', 'custom', 'success', now() - interval '2 minutes', now() - interval '2 minutes' + interval '8 seconds', 8, 0, 0, 6, 3, 0, NULL, now() - interval '2 minutes', now() - interval '2 minutes')
ON CONFLICT DO NOTHING;

-- Note: materialized views are not created here; the seeder will create/refresh the matviews when run.
-- If you want to pre-create matviews for demo data, add CREATE MATERIALIZED VIEW statements here.
