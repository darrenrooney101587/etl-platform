# agency_data_job

This job coordinates extraction and normalization of an agency's dataset and writes the resulting artifacts to S3 and/or the configured data sinks.

## Purpose

- Fetch domain records for a single `agency_id` from the source database or upstream APIs.
- Run transforms and enrichment processors.
- Upload produced artifacts (CSV/NDJSON) to a destination S3 path and emit run metadata to the job history table.

## Typical invocation

### Docker (preferred for production-like runs)

```bash
docker run --rm etl-pipeline-processing \
  pipeline-processing run agency_data_job --agency-id 123 --run-id run-20260118-123
```

### Local (Poetry)

```bash
cd packages/pipeline_processing
PYTHONPATH=../.. poetry run python -m pipeline_processing.cli.main run agency_data_job --agency-id 123
```

## Arguments

- `--agency-id <int>` (required): Agency identifier to process.
- `--run-id <string>` (optional): External run identifier for correlation.
- `--dry-run`: Run without side effects (no uploads, no DB writes).
- `--config <path>`: Optional path to a job config file (overrides environment defaults).

## Logic

1. Validate inputs and construct typed `AgencyJobConfig`.
2. Instantiate dependencies via DI (DatabaseClient, S3 client, repositories).
3. Call `AgencyProcessor.process_agency(agency_id, config)` which:
   - fetches rows via repositories
   - performs data shaping and enrichment
   - writes output files to a temporary local path
4. Upload artifacts to the configured S3 destination and persist job run metadata (success/failure, counts, timings).
5. Return an exit code mapping (0 = success, non-zero = failure).

## Observability

- Emit structured logs with `trace_id` / `run_id` when provided.
- Persist per-run metrics to the job history table for later inspection.

## Notes

- The job uses constructor injection for external clients to make unit testing straightforward.
- Unit tests should mock `DatabaseClient` and S3 client and verify calls to `AgencyProcessor`.
