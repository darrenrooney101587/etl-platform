#!/usr/bin/env bash
# scripts/commands.sh
# Concise developer runbook for file-processing: local, docker, and localstack tests.

# -----------------------
# A) Run locally (poetry / virtualenv)
# -----------------------
# Run the job using local python (fast feedback)
poetry run file-processing run s3_data_quality_job -- \
  --event-file packages/file_processing/event.json \
  --dry-run --trace-id local-test

# -----------------------
# B) Docker: build and run
# -----------------------
# Build image (from repo root)
# docker build -f docker/file-processing.Dockerfile -t etl-file-processing .

# Run image (macOS: use host.docker.internal to reach host Postgres)
# Mount repo so package .env is visible (no inline -e needed)
docker run --rm -v "$PWD":/app -w /app \
  --env-file packages/file_processing/.env \
  -e PYTHONPATH=/app/packages \
  etl-file-processing \
  run s3_data_quality_job -- \
    --event-file packages/file_processing/event.json \
    --dry-run --trace-id docker-test

# Dev variant: mount local packages so you don't have to rebuild after edits
docker run --rm -it -v "$PWD":/app -w /app \
  --env-file packages/file_processing/.env \
  -e PYTHONPATH=/app/packages \
  --entrypoint python etl-file-processing -m file_processing.cli.main \
  run s3_data_quality_job -- --event-file packages/file_processing/event.json --dry-run --trace-id docker-dev

# -----------------------
# C) Localstack + SNS listener (end-to-end test)
# -----------------------
# Start local infra (compose includes localstack if configured)
# from repo root; this will start services defined in compose/docker-compose.yml
docker-compose -f compose/docker-compose.yml up -d

# Start your SNS listener (if you have an infra script for it)
# adapts to the project's existing infra script; replace with your script if different
# infra/file_processing/scripts/sns_probe_listener.sh should exist in repo
bash infra/file_processing/scripts/sns_probe_listener.sh start

# Publish a test SNS message to the localstack endpoint (replace TOPIC_ARN)
# Ensure AWS CLI is configured or use --endpoint-url for localstack
aws --endpoint-url=http://localhost:4566 sns publish \
  --topic-arn arn:aws:sns:us-east-1:000000000000:your-topic \
  --message '{"Records": [{"s3": {"bucket": {"name": "ignored"}, "object": {"key": "from_client/nm_albuquerque/Officer_Detail.csv"}}}]}'
