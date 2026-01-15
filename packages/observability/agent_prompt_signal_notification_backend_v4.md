# Agent Prompt (V3): Build the Signal Notification System Backend (DB + API + Slack + Schedules) with Docker + Terraform

## Your Role
You are a senior backend engineer responsible for implementing a **Signal-based notification system** for ETL/data-processing workflows.

You must implement:
- Database models and migrations
- Job-based ingestion + query surfaces (preferred)
- Deterministic fingerprinting + Signal Grouping
- Ownership routing (tenant/job → owner/team)
- Slack connector **with interactivity** (Acknowledge button)
- Reminder + digest schedulers
- Dockerized runtime (worker + optional web surface)
- Terraform for **notification-system-specific resources only** (no VPC/NAT/network primitives)

Constraints:
- Do **not** use the term “incident.” Use **Signal** and **Signal Group**.
- Slack is not the system of record. The database is.
- Slack shared channel must remain low-volume; repeated occurrences must not spam it.

Deliver production-ready code with tests and clear configuration.

---

## 0) Architecture (Target State)

### Components
1. **Jobs / Ingestors (preferred)**
    - Periodic or event-driven jobs that read existing internal tables (for example `pipeline_errors`, monitoring tables, or ETL job state tables) and produce `Signal` records in the notification DB.
    - Jobs live under `packages/observability/jobs/` and export the `JOB` contract (entrypoint, description).
    - Jobs call processors and repositories to compute fingerprints, upsert SignalGroups, and enqueue Slack tasks.

2. **Worker / Scheduler**
    - Sends reminders (owner DM) and digests (shared channel)
    - Handles Slack message updates and retries
    - Runs periodically (Celery beat or cron-like scheduler)

3. **Slack Connector (required)**
    - Responsible for posting/updating messages and sending DMs.
    - Must be implemented as a connector/service in `packages/observability/services/` or `connectors/` and be callable from jobs/workers.
    - Slack interactive callbacks (Ack button) are optional in this package — preferred default: have your existing Django webserver handle Slack interaction callbacks and map them to DB updates. If you must receive Slack callbacks here, expose a minimal, secure endpoint and keep it thin.

> Note: An HTTP ingestion API (POST /api/signals) is optional. Use it only if other systems outside the monorepo cannot write to the source tables or cannot run jobs. The default recommended model is jobs-only ingestion that reads internal tables like `pipeline_errors`.

### Event Flow (jobs-first default)
Producer (writes to source tables) → periodic job reads `pipeline_errors` (or other sources) → create `Signal` rows → upsert `SignalGroup` → decide notifications → enqueue Slack send/update → Slack message links to Notifications UI (served by the existing Django webserver).

If external producers exist, an optional ingestion HTTP endpoint may be provided (see APIs section) but it is not required for the normal operation of the notification system.

---

## 1) Data Model (Must Implement)

Implement as Django models with explicit indexes and constraints.
You may adapt naming to match project conventions, but keep semantics identical.

### 1.1 `Signal`
Append-only record of each occurrence.

Fields (required unless noted):
- `id` (UUID primary key)
- `created_at` (auto_now_add)
- `occurred_at` (datetime; default now if not provided)
- `source` (varchar; e.g., airflow, dq, manual)
- `signal_type` (varchar/enum; e.g., job_failed, job_warning, sla_missed, dq_drop)
- `severity` (smallint enum: 0=S0 critical, 1=S1 high, 2=S2 medium, 3=S3 low)  **Lower is worse**
- `tenant_id` (uuid/int)
- `tenant_code` (varchar; denormalized display string)
- `job_name` (varchar)
- `run_id` (varchar; nullable)
- `task_id` (varchar; nullable)
- `stage` (varchar; nullable; failing stage if available)
- `error_class` (varchar; nullable; normalized exception/classifier)
- `error_message` (text; nullable; raw or excerpt)
- `fingerprint` (char/varchar; indexed; deterministic)
- `summary` (varchar; short human summary)
- `details_json` (jsonb; full structured payload)

Indexes:
- `idx_signal_fingerprint_occurred_at` on (`fingerprint`, `occurred_at` DESC)
- `idx_signal_tenant_occurred_at` on (`tenant_id`, `occurred_at` DESC)
- `idx_signal_job_occurred_at` on (`job_name`, `occurred_at` DESC)

### 1.2 `SignalGroup`
Stateful rollup keyed by fingerprint. This is the â€œunit of work.â€

Fields:
- `id` (UUID PK)
- `fingerprint` (varchar; indexed)
- `status` (enum: open, acknowledged, snoozed, closed)
- `current_severity` (smallint; same scale as Signal.severity)
- `tenant_id` (uuid/int; nullable if you later support cross-tenant grouping; for MVP keep non-null)
- `tenant_code` (varchar; denormalized)
- `job_name` (varchar; denormalized)
- `signal_type` (varchar; denormalized)
- `first_seen_at` (datetime)
- `last_seen_at` (datetime)
- `count_total` (int)
- `count_24h` (int; optional stored field; if stored, update on ingestion + periodic backfill; otherwise compute in queries)
- `last_signal_id` (FK to Signal; nullable)
- ownership:
    - `assigned_to_user_id` (FK/UUID; nullable)
    - `assigned_team_id` (FK/UUID; nullable)
- acknowledgement:
    - `acknowledged_at` (datetime; nullable)
    - `acknowledged_by_user_id` (FK/UUID; nullable)
- snooze:
    - `snoozed_until` (datetime; nullable)
- notification timestamps (for rate limiting):
    - `opened_notified_at` (datetime; nullable)  # initial shared-channel post
    - `last_reminded_at` (datetime; nullable)    # DM reminder rate limit
    - `last_daily_reminder_date` (date; nullable) # for â€œonce per dayâ€ caps
    - `last_escalated_at` (datetime; nullable)
- Slack linkage:
    - `slack_channel_id` (varchar; nullable)
    - `slack_root_ts` (varchar; nullable)  # message ts
- UI:
    - `ui_url` (varchar; cached deep link)

Indexes:
- `idx_group_status_severity_last_seen` on (`status`, `current_severity`, `last_seen_at` DESC)
- `idx_group_assignee_status_last_seen` on (`assigned_to_user_id`, `status`, `last_seen_at` DESC)
- `idx_group_tenant_status_last_seen` on (`tenant_id`, `status`, `last_seen_at` DESC)
- `idx_group_fingerprint_status` on (`fingerprint`, `status`)

Constraint:
- Ensure only one *active* group per fingerprint (open/ack/snoozed) if using reopen semantics:
    - either a partial unique index (preferred in Postgres)
    - or enforce in code with transactional upsert

### 1.3 `SignalGroupActivity`
Audit trail of state changes and system actions.

Fields:
- `id` (UUID PK)
- `signal_group_id` (FK)
- `created_at`
- `actor_type` (enum: system, user)
- `actor_user_id` (nullable)
- `action` (varchar; e.g., opened, acknowledged, snoozed, assigned, escalated, closed, reopened, slack_posted, slack_updated, dm_reminded, digest_sent)
- `metadata_json` (jsonb; e.g., previous status, slack ids, rule triggered)

Indexes:
- `idx_activity_group_created_at` on (`signal_group_id`, `created_at` DESC)

### 1.4 Ownership Mapping
Implement a minimal ownership model. Exact integration to your auth/user model may vary.

`TenantOwner`
- `tenant_id` (unique)
- `primary_owner_user_id`
- `secondary_owner_user_id` (nullable)
- `owning_team_id` (nullable)
- `updated_at`

Optional override for fine control:
`JobOwnerOverride`
- `tenant_id` (nullable for global override)
- `job_name`
- `owner_user_id` (nullable)
- `team_id` (nullable)
- unique constraint on (`tenant_id`, `job_name`)

### 1.5 Slack User Mapping
`UserSlackMap`
- `user_id` (unique)
- `slack_user_id` (unique)
- `created_at`

---

## 2) Business Logic Rules (Must Implement Exactly)

### 2.1 Fingerprinting (Deterministic Dedupe Key)
Compute `fingerprint` from stable components. Default formula:

`fingerprint = sha256("{tenant_id}|{signal_type}|{job_name}|{stage}|{error_class}|{normalized_error_message}")`

Normalization rules (implement as a module with unit tests):
- Lowercase
- Trim whitespace
- Remove run ids, UUIDs, timestamps, numeric ids where they cause false uniqueness
- Collapse repeated whitespace
- Optionally bucket numeric values (e.g., â€œtimeout after 30sâ€ â†’ â€œtimeout after <n>sâ€)

Store:
- `error_class` (best-effort classifier)
- `normalized_error_message` (not necessarily stored verbatim; can be re-derived)

### 2.2 Grouping + Reopen Policy
A Signal always gets stored.
A Signal Group is upserted by fingerprint.

Rules:
- If an active group exists for fingerprint (status in open/acknowledged/snoozed):
    - update that group
- Else if the most recent group is closed AND `now - closed_at <= REOPEN_WINDOW_HOURS` (default 24):
    - reopen it (status=open unless previously acknowledged; use open by default)
- Else:
    - create a new group (status=open)

### 2.3 Group Update Rules on Each New Signal
On ingestion:
- `last_seen_at = max(last_seen_at, occurred_at)`
- `count_total += 1`
- `current_severity = min(current_severity, signal.severity)`  (lower = worse)
- `last_signal_id = signal.id`
- keep denormalized display fields in sync (tenant_code/job_name/signal_type)

### 2.4 Notification Channel Policy (No Shared-Channel Spam)
Shared Slack channel receives posts ONLY for:
1. Group opened (first post)
2. Severity escalated (group severity becomes worse)
3. Daily digest (once/day)

Repeated signals must never generate new shared-channel posts.

### 2.5 Owner Routing Rules
Determine assignee and routing targets at group creation (and optionally on ack):
Priority:
1. JobOwnerOverride (tenant-specific first, then global)
2. TenantOwner.primary_owner_user_id
3. TenantOwner.owning_team_id
4. Unassigned triage queue (config)

Persist assignee on the group:
- If group is unassigned and someone acknowledges, optionally auto-assign to that person (config flag).

### 2.6 Acknowledgement Semantics (UI + Slack)

Acknowledgement is a workflow marker meaning:
> â€œSeen and being handled.â€

It is **not** resolution and it is not permissioned: anyone can acknowledge a Signal Group.

### Backend State Change (Idempotent)
When acknowledgement is requested (via UI or Slack):
- if `status=open` â†’ set `status=acknowledged`
- if `status=acknowledged` or `status=closed` â†’ no-op (return current state)
- set `acknowledged_at = now`
- set `acknowledged_by_user_id = actor_user_id`
- write `SignalGroupActivity(action="acknowledged", actor=user)`

### Assignment Policy (Default)
Acknowledgement must not change assignment by default:
- keep `assigned_to_user_id` unchanged
- exception: if `assigned_to_user_id` is null, you may auto-assign to acknowledger (config flag)

### Slack Side Effects
Acknowledgement must not post new shared-channel messages.
- Update the existing root Slack message via `chat.update`:
    - set status line: `Acknowledged by <@user> at <time>`
    - disable/remove the Acknowledge button
- Thread reply is optional (default off)
- Optional DM to assignee only when acknowledger â‰  assignee (or for S0/S1)

Tenant channels are not updated on acknowledgement by default.

## 3) APIs (Optional — jobs-first)

APIs are optional for the notification system when using jobs-only ingestion. The existing Django webserver will remain the operational UI surface for end users (ack, snooze, assign, etc.). Implement APIs here only if one of the following is true:
- External systems (outside your control) must push signals into the notification system, or
- You decide to accept Slack interaction callbacks in this package instead of via the Django webserver.

If you decide to provide an HTTP surface in `packages/observability/`, prefer a very small FastAPI app or a minimal Django bootstrap (per repo rules). Keep the handlers thin and delegate to processors/repositories.

Optional endpoints (implement only if required):
- `POST /api/signals` — ingestion (auth: internal token/mTLS). Use only when external producers cannot write to source tables or run jobs.
- `POST /api/slack/interactions` — Slack interactive callbacks (verify signature). Preferred default: let the Django webserver receive Slack callbacks and update the DB; this package should then process queued Slack updates.
- `GET /api/signal-groups` / `GET /api/signal-groups/<id>` — only implement if you need this package to directly support a separate UI; otherwise reuse the existing Django UI which reads the same DB.

Key rule: Do not duplicate the Django UI endpoints in this package unless there's a clear operational reason. Keep this package focused on jobs, processors, repositories, and connectors.

---

## 4) Slack Connector Requirements (Must Implement)

### 4.1 Posting Root Message (Shared Channel)
On group open:
- Post a Slack message with:
    - severity badge (S0/S1/S2/S3)
    - tenant + job + signal_type
    - summary (short)
    - count_total + last_seen_at
    - **Acknowledge button**
    - â€œOpen in Notifications link/button (deep link includes signal_group_id)

Persist returned:
- `slack_channel_id`
- `slack_root_ts`

### 4.2 Updating Root Message
On acknowledgement and on severity escalation (optional):
- `chat.update` the original message
- Update status line
- Disable/remove Acknowledge button

### 4.3 DM Reminders
- Resolve internal user â†’ Slack user id via `UserSlackMap`
- Open DM channel and send reminder message with link
- Rate limit using `last_reminded_at`

### 4.4 Slack Block Kit (Guidance)
Use a stable `action_id` like: `signal_group_ack`
Set button `value` to the group id.

Example (pseudocode):
- section: title + fields
- context: last_seen + count
- actions:
    - button(text="Acknowledge", action_id="signal_group_ack", value="<group_id>")
    - button(text="Open in Notifications", url="<ui_url>")

---

## 5) Schedules and Workers

You must implement scheduled jobs:
1. **Reminder dispatcher** (every 15 minutes)
    - selects groups needing owner DM reminders per rules
2. **Daily shared-channel digest** (once/day)
    - summary of open groups by severity + top repeaters + link
3. Optional: **Per-owner daily digest** (once/day)

Implementation options:
- Celery + Redis (preferred if already in stack)
- Or Django management commands invoked by scheduler

---

## 6) Docker Requirements (Use Existing / Worker-first)

- Use the existing `packages/observability/observability.Dockerfile` as the base image.
- The notification system may be deployed as either:
  - a worker-only image (preferred when jobs + workers handle all work), or
  - an image that includes a small HTTP surface for optional endpoints (only if you implement them).
- Provide `docker-compose.yml` in `packages/observability/` for local dev containing:
    - worker service (Celery worker/beat or scheduler)
    - optional api service (only if you expose endpoints)
    - postgres (or reuse existing)
    - redis (if using celery)
- Environment variables with sane defaults for local development

Required env vars (only the ones relevant to jobs/workers + slack):
- `DATABASE_URL`
- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET` (if you host Slack callbacks here)
- `SLACK_SHARED_CHANNEL_ID`
- `APP_BASE_URL` (for deep links)
- reminder/digest tuning vars:
    - `REOPEN_WINDOW_HOURS` (default 24)
    - `ACTIVE_WINDOW_MINUTES` (default 120)
    - `REMINDER_T2_HOURS` (default 2)
    - `REMINDER_T8_HOURS` (default 8)
    - `DAILY_DIGEST_TIME` (default 09:00 local)

---

## 7) Terraform Requirements (Notification-System Resources Only)

Do NOT implement networking primitives. Assume VPC/subnets/SGs exist and are passed in as variables.

Terraform should provision resources required specifically for this notification system, such as:
- Container execution resources (choose one based on org standard):
    - ECS Fargate service + task definitions (api + worker), OR
    - EKS deployment manifests via Helm (if thatâ€™s your standard; describe inputs)
- CloudWatch Log Groups for api/worker
- IAM roles/policies for:
    - pulling secrets
    - writing logs
    - (optional) SQS queue access
- Secrets management for Slack tokens:
    - AWS Secrets Manager secret (name + access policy)
- Optional but recommended for reliability:
    - SQS queue for async Slack send/update tasks
    - DLQ for failed notifications
    - EventBridge schedule for daily digest trigger (if not using Celery beat)

Deliverable: a `terraform/` module that can be applied independently with variables:
- `app_name`, `environment`
- `image_uri_api`, `image_uri_worker`
- `cpu`, `memory`, `desired_count`
- `vpc_id`, `subnet_ids`, `security_group_ids` (inputs only)
- `database_url` (or secret ref)
- `slack_secret_arn`
- optional: `sqs_enabled`, `sqs_visibility_timeout`, `schedule_expression`

---

## 8) Testing and Acceptance (Must Implement)

### Unit Tests
- fingerprint normalization stability
- grouping: create vs update
- reopen behavior
- routing selection order
- acknowledgement idempotency
- reminder eligibility and rate-limits

### Integration Tests (mock Slack)
- open group posts root message once
- repeated signals do not post to shared channel
- ack interaction updates group + triggers chat.update
- digest posts once/day

### Acceptance Criteria
- Repeated daily failures result in one shared-channel message per group, not spam
- Owners are kept informed via DM reminders/digests
- Acknowledge button works end-to-end and updates both DB + Slack message
- Notifications UI endpoints expose full context and history

---

## 9) Implementation Notes (Important)
- Use DB transactions for upsert + notification decisions to avoid race conditions when multiple signals arrive concurrently.
- Slack failures must not block ingestion; enqueue and retry.
- Keep normalization rules conservative initially; add test cases for real payloads as you learn.
- Always include UI deep links; keep Slack payloads short (no full stack traces).

---

## Output Expectations
Deliver:
- Job modules in `packages/observability/jobs/` that ingest from internal tables (e.g., `pipeline_errors`) and export `JOB` tuples
- Processors in `packages/observability/processors/` that compute fingerprints and apply grouping logic
- Repositories in `packages/observability/repositories/` that accept a `DatabaseClient` via DI and contain domain SQL
- Slack connector module in `packages/observability/services/` or `connectors/` (posting, updating, DM reminders)
- Worker/scheduler implementation in `packages/observability/jobs/` or `cli/` (Celery or scheduled jobs)
- Dockerfile updates + `packages/observability/docker-compose.yml` (worker-first)
- Terraform module in `infra/observability/`
- Tests in `packages/observability/tests/` (unit + integration with mocked Slack)
- A short README explaining configuration and local run steps
