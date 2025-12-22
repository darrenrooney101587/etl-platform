# File Delivery Monitoring System

This repository provides a reference implementation for monitoring client file deliveries into Amazon S3. It mixes event-driven ingestion with scheduled sweeps to detect missing or late files using explicit, per-stream expectations.

## Architecture Overview

- **Expectation configuration**: Streams are defined by client, bucket, prefix/pattern, timezone, cadence (daily cutoff or max-gap), cutoff or gap thresholds, and alert routing.
- **Arrival ingestion**: S3 ObjectCreated notifications feed an SQS queue. The `ArrivalConsumer` parses events, qualifies keys, records delivery events, and updates per-stream state immediately.
- **Sweeper**: Runs every few minutes to mark streams overdue when `computed_overdue_at_utc` has passed and emits alerts with escalation support.
- **Admin API**: FastAPI surface to CRUD expectations, inspect state, ingest test events, and trigger the sweeper.
- **Infrastructure**: Terraform sample wiring S3 notifications to SQS plus a CloudWatch Events rule for the sweeper trigger.

## Expectation Model

### Daily cutoff (calendar-based)

- Uses the client timezone. Delivery day is the local calendar day.
- Due time: `cutoff_time_local` for that day.
- Overdue: due time plus `grace_minutes`.
- After a qualifying arrival, the next due is the following calendar day's cutoff, ensuring yesterday's late file does not satisfy today's SLA.

### Max-gap (high frequency)

- Active window is defined by `active_start_local`, `active_end_local`, and optional `active_days_of_week` (0=Monday).
- Within an active window, `max_gap_minutes` sets the allowed distance from the last arrival. Outside the window, the next due is the start of the next window plus the gap.
- Grace can optionally shift the overdue threshold.

## Data Model

- **Expectation**: Persistent configuration for each `(client_id, stream_id)`.
- **StreamState**: Derived state including last arrival, computed due/overdue timestamps, and alert metadata.
- **DeliveryEvent**: Append-only record of qualified and rejected arrivals.
- **AlertEvent**: History of overdue episodes and escalations.

## Running Tests

Install optional dev dependencies and execute pytest:

```bash
pip install -e .[dev]
pytest
```

## Local testing

### Run directly with uvicorn

```bash
pip install -e .[dev]
LOAD_MOCK_DATA=true uvicorn file_monitoring.api:app --host 0.0.0.0 --port 8000 --reload
```

The `LOAD_MOCK_DATA` flag seeds in-memory expectations and example arrivals so `/state` and `/alerts/{client}/{stream}` return data immediately. To refresh the seeded data during a session, call:

```bash
curl -X POST http://localhost:8000/mock/reseed
```

### Run with Docker Compose

```bash
docker compose up --build
```

The compose file exposes the FastAPI admin surface on `http://localhost:8000`. It also turns on mock data seeding by default. Useful endpoints:

- `GET /expectations` – view configured mock expectations
- `GET /state` – inspect computed due/overdue timestamps and status
- `POST /ingest` – send an S3 event payload (e.g., `sample_events.json`) to simulate arrivals
- `POST /sweeper/run` – manually trigger the sweeper to evaluate overdue streams

## Notes

- All time arithmetic uses UTC internally; timezone conversion only occurs in SLA calculations.
- Idempotency is enforced in the in-memory delivery event store to handle duplicate S3 notifications.
- Alert escalation honors acknowledgements and snoozes tracked on the stream state.
