# Observability Notification Backend (Job-Driven)

Backend processing layer for Signal/Signal Group notifications. Runs as ad-hoc or scheduled Kubernetes Jobs/CronJobs (no web endpoints or long-lived services).

## Responsibilities
- Ingest operational signals into existing `notification_*` tables
- Fingerprint + group signals deterministically
- Maintain lifecycle and ownership routing
- Send/update Slack messages (shared channel + owner DMs)
- Dispatch reminders and daily digest on fixed schedules

## Jobs

The package exposes the following jobs (executed via Kubernetes Jobs/CronJobs):

- `ingest_airflow`: Ingest Airflow failures and alerts
- `ingest_cloverdx`: Ingest CloverDX job signals
- `ingest_dq`: Ingest data quality failures
- `reminder_dispatcher`: Send owner DM reminders
- `daily_digest`: Send shared-channel daily digest

Use the package CLI helper for discovery:
```bash
PYTHONPATH=packages python -m observability.cli.main list
PYTHONPATH=packages python -m observability.cli.main run reminder_dispatcher
```

## Configuration

Environment variables:

- `DATABASE_URL`: Postgres connection string
- `SLACK_BOT_TOKEN`: Bot token for Slack API
- `SLACK_SIGNING_SECRET`: Signing secret for Slack interactivity
- `SLACK_SHARED_CHANNEL_ID`: Shared notification channel ID
- `APP_BASE_URL`: Base URL for UI links
- `REOPEN_WINDOW_HOURS` (default `24`): Hours before reopening a closed signal group if it recurs
- `REMINDER_T2_HOURS` (default `2`): First reminder threshold
- `REMINDER_T8_HOURS` (default `8`): Second reminder threshold
- `DAILY_DIGEST_TIME` (default `09:00`): Time of day for digest

## Schema

Authoritative tables live in the shared schema repo (`reporting.notification_*`). This backend treats them as authoritative and does not rename or repurpose fields.

### Core Tables

**notification_signal**
- `id` (UUID PK)
- `created_at`, `occurred_at`
- `source`, `signal_type`, `severity`
- `agency_id`, `agency_slug`
- `job_name`, `run_id`, `task_id`, `stage`
- `error_class`, `error_message`
- `fingerprint` (deterministic grouping key)
- `summary`, `details_json`

**notification_signal_group**
- `id` (UUID PK)
- `fingerprint` (unique grouping key)
- `status` (`open`, `acknowledged`, `snoozed`, `closed`)
- `current_severity`
- `agency_id`, `agency_slug`
- `job_name`, `signal_type`
- `first_seen_at`, `last_seen_at`
- `count_total`, `count_24h`
- `last_signal_id`
- Ownership: `assigned_to_user_id`, `assigned_team_id`
- Acknowledgement: `acknowledged_at`, `acknowledged_by_user_id`
- Snooze: `snoozed_until`
- Rate limiting: `opened_notified_at`, `last_reminded_at`, `last_daily_reminder_date`, `last_escalated_at`
- Slack linkage: `slack_channel_id`, `slack_root_ts`
- UI: `ui_url`
- Backend-only additions: `closed_at`, `last_slack_updated_at`, `slack_message_hash`
- **Constraint:** partial unique index on `(agency_id, fingerprint)` where status in (`open`, `acknowledged`, `snoozed`)

**notification_signal_group_activity**
- `id` (UUID PK)
- `signal_group_id`
- `created_at`
- `actor_type` (`system`, `user`)
- `actor_user_id`
- `action` (opened, escalated, acknowledged, snoozed, closed, reopened, slack_posted, slack_updated, reminder_sent, digest_sent)
- `metadata_json`

### Ownership & Slack Mappings

- `notification_agency_owner`: Primary/secondary owners, owning team
- `notification_job_owner_override`: Per-job overrides, optional agency_id
- `notification_user_slack_map`: user_id ↔ slack_user_id

### Fingerprinting

Signals are grouped deterministically using:

```
sha256("{agency_id}|{signal_type}|{job_name}|{stage}|{error_class}|{normalized_error_message}")
```

Normalization rules: lowercase, strip UUIDs/run IDs/timestamps, collapse whitespace, bucket numbers.
