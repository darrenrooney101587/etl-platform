#!/usr/bin/env bash
# scripts/commands.sh
# Developer command reference for file processing and data-quality operations.
# Copy/paste these commands for testing and development.

# ------------------------------------------------------------------
# Local CLI (poetry) - run installed console scripts from package
# ------------------------------------------------------------------

# Run the file-processing CLI (console script provided by packages/file_processing)
poetry run file-processing --help

# Run SNS HTTP listener locally (for receiving SNS messages in dev)
poetry run file-processing-sns

# Run the s3_data_quality_job using the installed console script
# Pass an AWS-style event JSON to mimic SNS/SQS/S3 flow
poetry run file-processing run s3_data_quality_job -- \
  --event-json '{"Records": [{"s3": {"bucket": {"name": "ignored"}, "object": {"key": "from_client/nm_albuquerque/Officer_Detail.csv"}}}]}'

# ------------------------------------------------------------------
# Docker: build images (run from repo root so COPY paths work)
# ------------------------------------------------------------------

# Build the file-processing runtime image (must run from repo root so COPY packages/.. paths exist)
docker build -f docker/file-processing.Dockerfile -t etl-file-processing .

# Build the data-pipeline image (if you need the other runtime)
docker build -f docker/data-pipeline.Dockerfile -t etl-data-pipeline .

# ------------------------------------------------------------------
# Docker: run the file-processing image (production / baked image)
# ------------------------------------------------------------------

# Quick help / verify image entrypoint
docker run --rm etl-file-processing --help

# Run s3_data_quality_job in the container (use repo mounted and env-file for local config)
# - Mount project so LOCAL_S3_ROOT and local code are accessible
# - Set PYTHONPATH so packages on /app/packages import correctly
# - Use --entrypoint override if you want to call python -m directly

docker run --rm -v "$PWD":/app -w /app \
  --env-file packages/file_processing/.env \
  -e DB_HOST=host.docker.internal \
  -e PYTHONPATH=/app/packages \
  etl-file-processing \
  run s3_data_quality_job -- \
    --event-json '{"Records": [{"s3": {"bucket": {"name": "ignored"}, "object": {"key": "from_client/nm_albuquerque/Officer_Detail.csv"}}}]}' \
    --dry-run --dry-run-output ./dry_run_results.jsonl -v

# Run the SNS HTTP listener inside the image (override entrypoint to start the SNS module)
# This runs a simple HTTP server that accepts SNS POSTs (SubscriptionConfirmation + Notification)
# Use -p to expose a port if you want to receive messages from AWS via a public endpoint or ngrok.

docker run --rm -it -v "$PWD":/app -w /app \
  --env-file packages/file_processing/.env \
  -e PORT=8080 -e PYTHONPATH=/app/packages \
  --entrypoint python \
  etl-file-processing -m file_processing.cli.sns_main

# ------------------------------------------------------------------
# Docker: dev container pattern (mount packages, run in-repo code)
# ------------------------------------------------------------------

# Dev run: mount local packages and run the job with the repo code (no image rebuild required)
# This mirrors the production code path while using local source and .env settings

docker run --rm -it \
  -v "$PWD":/app \
  -w /app \
  --env-file packages/file_processing/.env \
  -e DB_HOST=host.docker.internal \
  -e PYTHONPATH=/app/packages \
  --entrypoint python \
  etl-file-processing -m file_processing.cli.main run s3_data_quality_job -- \
    --event-json '{"Records": [{"s3": {"bucket": {"name": "ignored"}, "object": {"key": "from_client/nm_albuquerque/Officer_Detail.csv"}}}]}' \
    --dry-run --dry-run-output ./dry_run_results.jsonl -v

# ------------------------------------------------------------------
# Docker: run the data-pipeline image (if you need the other service)
# ------------------------------------------------------------------

# Help
docker run --rm etl-data-pipeline --help

# Example: run an installed console script inside data-pipeline image
docker run --rm etl-data-pipeline data-pipeline-get-s3-files --agency-id 10 \
  --source-bucket my-source-bucket --destination-bucket my-destination-bucket

# ------------------------------------------------------------------
# Notes
# - Always run the docker build commands from the repository root so COPY paths in Dockerfiles
#   (COPY packages/etl_core ...) resolve correctly.
# - Use the package-level `.env` files (e.g. `packages/file_processing/.env`) for local overrides
#   such as LOCAL_S3_ROOT and DB_* settings.
# - The container entrypoint for `file-processing` image is `python -m file_processing.cli.main`.
#   To run alternate modules (SNS listener) override the entrypoint as shown above.
# - For production on EKS, configure the container command to be the job invocation (e.g. the
#   `run s3_data_quality_job ...` args) and let the cluster handle scaling / concurrency.
# ------------------------------------------------------------------
