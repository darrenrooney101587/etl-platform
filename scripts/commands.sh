#!/usr/bin/env bash
# scripts/commands.sh
# Developer command reference for S3 file processing operations.
# Copy/paste these commands for testing and development.

# -----------------------------
# CLI Commands
# -----------------------------

# Dry run (analyze only, no file operations)
# The ServiceHandler supports dry_run; we show how to invoke it below from the container.

# Real run (process files and employment history) using the installed console script
poetry run data-pipeline-get-s3-files --agency-id 10

# With custom buckets
poetry run data-pipeline-get-s3-files \
  --agency-id 42 \
  --source-bucket my-source-bucket \
  --destination-bucket my-destination-bucket


# -----------------------------
# Docker: run the CLI inside a container image (production / baked image)
# -----------------------------

# Production image: run the installed console script (image must include the console script)
# Preferred: if the image sets the console script as ENTRYPOINT (recommended for EKS Jobs),
# pass only the CLI arguments to the container. This keeps the job invocation stable for K8s.
# Example (preferred):
docker run --rm etl-data-pipeline \
  --agency-id 10 \
  --source-bucket benchmarkanalytics-production-env-userdocument-test \
  --destination-bucket etl-ba-research-client-etl

# Fallback: if the image does NOT set the console script as ENTRYPOINT, invoke it explicitly:
# (this will run the console script as the container command)
# Example (fallback):
docker run --rm etl-data-pipeline \
  data-pipeline-get-s3-files --agency-id 10 \
  --source-bucket benchmarkanalytics-production-env-userdocument-test \
  --destination-bucket etl-ba-research-client-etl

# Production: with custom buckets (preferred ENTRYPOINT form)
docker run --rm etl-data-pipeline \
  --agency-id 42 \
  --source-bucket my-source-bucket \
  --destination-bucket my-destination-bucket

# Production: with custom buckets (fallback explicit invocation)
docker run --rm etl-data-pipeline \
  data-pipeline-get-s3-files --agency-id 42 \
  --source-bucket my-source-bucket \
  --destination-bucket my-destination-bucket


# -----------------------------
# Docker: dev container (mount local source, auto-install deps via entrypoint)
# -----------------------------

# Use the dev entrypoint so the container will install dependencies when the
# source is mounted into the container at runtime.
# Replace SKIP_INSTALL=1 to avoid installs when you know the image is already built.

docker run --rm -it \
  -v "$(pwd)/packages/data_pipeline:/app/packages/data_pipeline" \
  -v "$(pwd)/packages/etl_core:/app/packages/etl_core" \
  --workdir /app/packages/data_pipeline \
  -e SKIP_INSTALL= \
  --entrypoint /app/packages/data_pipeline/config_scripts/docker-entrypoint.sh \
  etl-data-pipeline \
  poetry run data-pipeline-get-s3-files --agency-id 10 \
    --source-bucket benchmarkanalytics-production-env-userdocument-test \
    --destination-bucket etl-ba-research-client-etl


# -----------------------------
# Docker: analyze (dry run) examples
# -----------------------------

# Production image: call ServiceHandler.analyze_agency_data inside the image and print JSON
docker run --rm etl-data-pipeline \
  python - <<'PY'
import json
from data_pipeline.service_handler import ServiceHandler
s = ServiceHandler(source_bucket="benchmarkanalytics-production-env-userdocument-test", destination_bucket="etl-ba-research-client-etl")
print(json.dumps(s.analyze_agency_data(10, dry_run=True)))
PY

# Dev container: mount source and run analyze via the dev entrypoint (auto installs if needed)
docker run --rm -it \
  -v "$(pwd)/packages/data_pipeline:/app/packages/data_pipeline" \
  -v "$(pwd)/packages/etl_core:/app/packages/etl_core" \
  --workdir /app/packages/data_pipeline \
  --entrypoint /app/packages/data_pipeline/config_scripts/docker-entrypoint.sh \
  etl-data-pipeline \
  poetry run python - <<'PY'
import json
from data_pipeline.service_handler import ServiceHandler
s = ServiceHandler(source_bucket="benchmarkanalytics-production-env-userdocument-test", destination_bucket="etl-ba-research-client-etl")
print(json.dumps(s.analyze_agency_data(10, dry_run=True)))
PY


# -----------------------------
# Docker: run module directly (falls back to python -m when console script not present)
# -----------------------------

docker run --rm etl-data-pipeline python -m data_pipeline.cli.get_s3_files --agency-id 10
