# Notification Schema Alignment (Authoritative Tables)

The frontend and webserver use existing tables in the shared schema repo. This backend treats them as authoritative and does **not** rename or repurpose fields.

## Tables

- `notification_signal`
  - `id UUID PK`
  - `created_at`, `occurred_at`
  - `source`, `signal_type`, `severity`
  - `agency_id`, `agency_slug`
  - `job_name`, `run_id`, `task_id`, `stage`
  - `error_class`, `error_message`
  - `fingerprint`
  - `summary`, `details_json`

- `notification_signal_group`
  - `id UUID PK`
  - `fingerprint`
  - `status` (`open`, `acknowledged`, `snoozed`, `closed`)
  - `current_severity`
  - `agency_id`, `agency_slug`
  - `job_name`, `signal_type`
  - `first_seen_at`, `last_seen_at`
  - `count_total`, `count_24h`
  - `last_signal_id`
  - Ownership: `assigned_to_user_id`, `assigned_team_id`
  - Ack: `acknowledged_at`, `acknowledged_by_user_id`
  - Snooze: `snoozed_until`
  - Rate limiting: `opened_notified_at`, `last_reminded_at`, `last_daily_reminder_date`, `last_escalated_at`
  - Slack linkage: `slack_channel_id`, `slack_root_ts`
  - UI: `ui_url`
  - **Backend-only additions (required):** `closed_at`, `last_slack_updated_at`, `slack_message_hash`
  - **Constraint:** partial unique index on `(agency_id, fingerprint)` where status in (`open`, `acknowledged`, `snoozed`)

- `notification_signal_group_activity`
  - `id UUID PK`
  - `signal_group_id`
  - `created_at`
  - `actor_type` (`system`, `user`)
  - `actor_user_id`
  - `action` (opened, escalated, acknowledged, snoozed, closed, reopened, slack_posted, slack_updated, reminder_sent, digest_sent)
  - `metadata_json`

- Ownership & Slack mappings
  - `notification_agency_owner` (primary/secondary owners, owning team)
  - `notification_job_owner_override` (per job overrides, optional agency_id)
  - `notification_user_slack_map` (user_id ↔ slack_user_id)

## Fingerprinting
`sha256("{agency_id}|{signal_type}|{job_name}|{stage}|{error_class}|{normalized_error_message}")`
Normalization rules: lowercase, strip UUIDs/run IDs/timestamps, collapse whitespace, bucket numbers.
