-- Seed data for reporting_seeder (development/dev-local only)
-- Adjust IDs and columns to match your schema; this file uses conservative columns from SCHEMA.md

-- Ensure test agency exists (may need additional columns in your real Agency table)
INSERT INTO public.agency (id, name, address, subdomain, lms_integration_enabled, active, lms_tenant_root_only)
VALUES (1, 'Test Agency', '123 Example St', 'testagency', false, true, false)
ON CONFLICT (id) DO NOTHING;

-- Canned reports (templates) - create multiple canned reports to exercise matview creation
INSERT INTO reporting.seeder_canned_report (id, table_name, report_name, query, database_id)
VALUES
  (100, 'reporting.canned_sales', 'Canned Sales', $$SELECT generate_series(1,1000) AS id, md5(random()::text) AS val$$, 1),
  (101, 'reporting.canned_customers', 'Canned Customers', $$SELECT i AS id, ('Customer "' || i) AS name FROM generate_series(1,500) AS s(i)$$, 1),
  (102, 'reporting.canned_orders', 'Canned Orders', $$SELECT i AS order_id, (i % 50) AS customer_id, NOW()::timestamp AS created_at FROM generate_series(1,2000) AS s(i)$$, 1),
  (103, 'reporting.canned_transactions', 'Canned Transactions', $$SELECT i AS txn_id, random() * 1000 AS amount FROM generate_series(1,800) AS s(i)$$, 1),
  (104, 'reporting.canned_products', 'Canned Products', $$SELECT i AS product_id, md5(random()::text) AS sku FROM generate_series(1,600) AS s(i)$$, 1)
ON CONFLICT (id) DO NOTHING;

-- Map canned reports to agency (manifests)
INSERT INTO reporting.seeder_canned_report_manifest (id, agency_id, agency_slug, canned_report_id)
VALUES
  (200, 1, 'test-agency', 100),
  (201, 1, 'test-agency', 101),
  (202, 1, 'test-agency', 102),
  (203, 1, 'test-agency', 103),
  (204, 1, 'test-agency', 104)
ON CONFLICT (id) DO NOTHING;

-- Custom report manifest (examples) - include additional custom manifests
INSERT INTO reporting.seeder_custom_report_manifest (
  id, table_name, report_name, agency_id, agency_slug, query, database_id, enabled
)
VALUES
  (300, 'reporting.custom_demo', 'Custom Demo', 1, 'test-agency', $$SELECT generate_series(1,200) AS id, md5(random()::text) AS val$$, 1, TRUE),
  (301, 'reporting.custom_activity', 'Custom Activity', 1, 'test-agency', $$SELECT i AS id, ('activity_' || i) AS activity FROM generate_series(1,1500) AS s(i)$$, 1, TRUE),
  (302, 'reporting.custom_metrics', 'Custom Metrics', 1, 'test-agency', $$SELECT i AS id, (random()*100)::int AS metric FROM generate_series(1,400) AS s(i)$$, 1, TRUE)
ON CONFLICT (id) DO NOTHING;

-- Create example job status rows (dashboard current state)
INSERT INTO reporting.seeder_job_status (
  table_name, manifest_id, report_name, report_type, agency_id, agency_slug, status, duration_seconds, start_time, consecutive_failures, last_run_id, last_errors, updated_at
)
VALUES
  ('reporting.canned_sales', 100, 'Canned Sales', 'canned', 1, 'test-agency', 'success', 0, now(), 0, NULL, NULL, now()),
  ('reporting.canned_customers', 101, 'Canned Customers', 'canned', 1, 'test-agency', 'success', 0, now(), 0, NULL, NULL, now()),
  ('reporting.canned_orders', 102, 'Canned Orders', 'canned', 1, 'test-agency', 'success', 0, now(), 0, NULL, NULL, now()),
  ('reporting.canned_transactions', 103, 'Canned Transactions', 'canned', 1, 'test-agency', 'success', 0, now(), 0, NULL, NULL, now()),
  ('reporting.canned_products', 104, 'Canned Products', 'canned', 1, 'test-agency', 'success', 0, now(), 0, NULL, NULL, now()),
  ('reporting.custom_demo', 300, 'Custom Demo', 'custom', 1, 'test-agency', 'success', 0, now(), 0, NULL, NULL, now()),
  ('reporting.custom_activity', 301, 'Custom Activity', 'custom', 1, 'test-agency', 'success', 0, now(), 0, NULL, NULL, now()),
  ('reporting.custom_metrics', 302, 'Custom Metrics', 'custom', 1, 'test-agency', 'success', 0, now(), 0, NULL, NULL, now())
ON CONFLICT (table_name) DO UPDATE SET updated_at = now();

-- Insert a couple of recent run history rows to populate the UI history list
INSERT INTO reporting.seeder_run_history (
  run_id, manifest_id, table_name, report_name, agency_id, agency_slug, report_type, status, start_time, finish_time, duration_seconds, records_processed, bytes_processed, memory_usage_mb, cpu_percentage, consecutive_failures, errors, created_at, updated_at
)
VALUES
  ('seed-run-1', 100, 'reporting.canned_sales', 'Canned Sales', 1, 'test-agency', 'canned', 'success', now() - interval '5 minutes', now() - interval '5 minutes' + interval '10 seconds', 10, 1000, 0, 5, 2, 0, NULL, now() - interval '5 minutes', now() - interval '5 minutes'),
  ('seed-run-2', 300, 'reporting.custom_demo', 'Custom Demo', 1, 'test-agency', 'custom', 'success', now() - interval '2 minutes', now() - interval '2 minutes' + interval '8 seconds', 8, 200, 0, 6, 3, 0, NULL, now() - interval '2 minutes', now() - interval '2 minutes')
ON CONFLICT DO NOTHING;

-- Note: materialized views are not created here; the seeder will create/refresh the matviews when run.
-- If you want to pre-create matviews for demo data, add CREATE MATERIALIZED VIEW statements here.
