# Observability Notification Backend (Job-Driven)

Backend processing layer for Signal/Signal Group notifications. Runs as ad-hoc or scheduled Kubernetes Jobs/CronJobs (no web endpoints or long-lived services).

## Responsibilities
- Ingest operational signals into existing `notification_*` tables
- Fingerprint + group signals deterministically
- Maintain lifecycle and ownership routing
- Send/update Slack messages (shared channel + owner DMs)
- Dispatch reminders and daily digest on fixed schedules

## Commands (executed via jobs)
- `python -m observability.jobs.ingest_airflow`
- `python -m observability.jobs.ingest_cloverdx`
- `python -m observability.jobs.ingest_dq`
- `python -m observability.jobs.reminder_dispatcher`
- `python -m observability.jobs.daily_digest`

Use the package CLI helper for discovery:
```bash
PYTHONPATH=packages python -m observability.cli.main list
PYTHONPATH=packages python -m observability.cli.main run reminder_dispatcher
```

## Configuration
- `DATABASE_URL`
- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- `SLACK_SHARED_CHANNEL_ID`
- `APP_BASE_URL`
- `REOPEN_WINDOW_HOURS` (default `24`)
- `REMINDER_T2_HOURS` (default `2`)
- `REMINDER_T8_HOURS` (default `8`)
- `DAILY_DIGEST_TIME` (default `09:00`)

## Schema
Authoritative tables live in the shared schema repo (`reporting.notification_*`). See `schema.md` for field alignment and backend-only additions.
