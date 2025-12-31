# data_pipeline

Combined transforms + ingestion runtime lane.
Compute + side‑effecting writes.

## Responsibilities
- S3‑based transforms (bronze → silver)
- Enrichment & normalization
- Backfills / reprocessing
- Application API ingestion
- Idempotency, batching, DLQ, audit trails

## Migration Notes
This package contains the migrated code from `etl-data-extraction`.
The legacy `service` app has been refactored into a pure Python module.
Django project artifacts (manage.py, etc.) have been removed.

## How to Run
### Local Development
```bash
poetry install --extras db
poetry run data-pipeline-get-s3-files --help
```

### Docker
```bash
docker build -f ../../docker/data-pipeline.Dockerfile -t etl-data-pipeline ../..
docker run --env-file .env etl-data-pipeline data-pipeline-get-s3-files --agency-id 10
```
