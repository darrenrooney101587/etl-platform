# s3_data_quality_job

This job orchestrates the processing of a single S3 file for data quality checks.
It is invoked by the SNS listener (for real-time events) or manually via CLI.

## Usage

### Run via Docker (Recommended)

```bash
docker run --rm etl-pipeline-processing \
  pipeline-processing run s3_data_quality_job \
  --event-json '{"Records": [{"s3": {"bucket": {"name": "my-bucket"}, "object": {"key": "my-key"}}}]}'
```

### Run Locally (Poetry)

```bash
cd packages/pipeline_processing
PYTHONPATH=../.. poetry run python -m pipeline_processing.cli.main run s3_data_quality_job \
  --event-json '{"Records": [{"s3": {"bucket": {"name": "my-bucket"}, "object": {"key": "my-key"}}}]}'
```

## Arguments

- `--event-json <JSON_STRING>`: JSON string of the S3 event (AWS S3 notification format).
- `--event-file <FILE_PATH>`: Path to a file containing the JSON event payload.
- `--dry-run`: Run without persisting changes to the database.
- `--trace-id <ID>`: Optional trace ID for logging context.

## Logic

1.  **Event Extraction**: Parses the input payload (direct dictionary, S3 event, or SNS-wrapped S3 event) to extract `S3Event` objects (bucket/key).
2.  **Validation**: Verifies the file exists in S3 (via `s3_client`).
3.  **Processing**: Delegates content parsing and validation to `S3DataQualityProcessor`.
4.  **Reporting**: Logs results and persists metrics to the database (unless `--dry-run` is active).
