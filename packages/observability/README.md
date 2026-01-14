# Observability

Signal-based notification system for ETL workflows.

## Features

- Signal ingestion API with deterministic fingerprinting and grouping
- Stateful `SignalGroup` workflow (open → acknowledged → snoozed/closed)
- Slack connector (shared channel post, acknowledgement update, DM reminders, daily digest)
- Ownership routing (tenant + job overrides)
- Reminder dispatcher and daily digest jobs (CLI + worker loop)
- Dockerized API/worker plus Terraform module for notification resources

## Running locally

```bash
# Start API, worker, Postgres, and Redis
cd compose
docker-compose up --build observability-api observability-worker postgres redis
```

The API listens on `http://localhost:8000`.

## Configuration

Environment variables (with safe defaults for local use):

- `DATABASE_URL` (defaults to SQLite when unset)
- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- `SLACK_SHARED_CHANNEL_ID`
- `APP_BASE_URL` (default `http://localhost:8000`)
- `INTERNAL_INGEST_TOKEN`
- `REOPEN_WINDOW_HOURS` (default `24`)
- `ACTIVE_WINDOW_MINUTES` (default `120`)
- `REMINDER_T2_HOURS` (default `2`)
- `REMINDER_T8_HOURS` (default `8`)
- `DAILY_DIGEST_TIME` (default `09:00`)

## Jobs and CLI

CLI entrypoint: `observability.cli.main` (console script `etl-observe`).

Available jobs:

- `reminder_dispatcher` – DM owners for open/ack groups (rate limited)
- `daily_digest` – Post shared-channel digest once per day

```bash
PYTHONPATH=packages python -m observability.cli.main list
PYTHONPATH=packages python -m observability.cli.main run reminder_dispatcher
```
