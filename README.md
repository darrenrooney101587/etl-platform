# ETL File Monitoring

Backend ingestion service for file monitoring data quality. The service polls SQS for S3 events, validates incoming files against schema definitions, and writes data quality metrics to the shared reporting database.

## Setup

1. Copy `.env.example` to `.env` and configure values.
2. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Commands

### Run the API server (health check)

```bash
python manage.py runserver
```

Health check endpoint:

```
GET /health/
```

### Run the SQS worker

```bash
python manage.py run_worker
```

### Trigger ingestion locally

```bash
python manage.py process_file --bucket your-bucket --key path/to/file.csv
```

If you omit `--bucket`, the command uses `S3_BUCKET_NAME` from `.env`.

### Load seed data and sample file

Use the provided fixture and sample CSV to exercise schema validation, bounds, completeness, and uniqueness deductions.

```bash
python manage.py seed_data
```

The sample CSV is located at `data/sample_monitoring_file.csv`. After seeding, trigger ingestion using the sample key:

```bash
python manage.py process_file --key data/sample_monitoring_file.csv
```

## Testing

```bash
python -m unittest
```

## Environment Variables

| Variable | Description |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django secret key. |
| `DJANGO_DEBUG` | Enable debug mode (`true`/`false`). |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated list of allowed hosts. |
| `DJANGO_TIME_ZONE` | Time zone for timestamps (default `UTC`). |
| `DB_NAME` | PostgreSQL database name. |
| `DB_USER` | PostgreSQL username. |
| `DB_PASSWORD` | PostgreSQL password. |
| `DB_HOST` | PostgreSQL host. |
| `DB_PORT` | PostgreSQL port. |
| `DB_CONN_MAX_AGE` | Connection max age (seconds). |
| `AWS_REGION` | AWS region for S3/SQS. |
| `SQS_QUEUE_URL` | URL of the SQS queue for S3 events. |
| `S3_BUCKET_NAME` | Default S3 bucket for local ingestion. |
| `DATA_QUALITY_PASSING_SCORE` | Threshold for pass/fail (default `80`). |
| `LOG_LEVEL` | Logging level (default `INFO`). |
