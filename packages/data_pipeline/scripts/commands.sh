#!/usr/bin/env bash
# scripts/commands.sh
# Developer command reference for S3 file processing operations.
# Copy/paste these commands for testing and development.

# -----------------------------
# CLI Commands
# -----------------------------

# Dry run (analyze only, no file operations) - Note: dry-run logic needs to be implemented in CLI if supported
# Currently the CLI does not expose a --dry-run flag explicitly in the argparse definition I created,
# but the ServiceHandler supports it. I should probably add it to the CLI.
# For now, I will list the commands that are supported.

# Real run (process files and employment history)
poetry run data-pipeline-get-s3-files --agency-id 10

# With custom buckets
poetry run data-pipeline-get-s3-files \
  --agency-id 42 \
  --source-bucket my-source-bucket \
  --destination-bucket my-destination-bucket


# Process endpoint (dry run via process API)
curl -X POST http://localhost:5090/api/s3/process/ \
  -H "Content-Type: application/json" \
  -d '{"agency_id": 10, "dry_run": true}'

# Process with custom buckets (real run)
curl -X POST http://localhost:5090/api/s3/process/ \
  -H "Content-Type: application/json" \
  -d '{
    "agency_id": 42,
    "dry_run": True,
    "source_bucket": "my-source-bucket",
    "destination_bucket": "my-destination-bucket"
  }'

# Process with custom buckets (dry run)
curl -X POST http://localhost:5090/api/s3/process/ \
  -H "Content-Type: application/json" \
  -d '{
    "agency_id": 42,
    "dry_run": true,
    "source_bucket": "my-source-bucket",
    "destination_bucket": "my-destination-bucket"
  }'

# -----------------------------
# With Basic Auth (if enabled)
# -----------------------------

# Set auth variables first:
# export AUTH_USER="your-username"
# export AUTH_PASS="your-password"
# AUTH_HEADER=$(printf "%s:%s" "$AUTH_USER" "$AUTH_PASS" | base64)

# Analyze with auth
# curl -X POST http://localhost:5090/api/s3/analyze/ \
#   -H "Content-Type: application/json" \
#   -H "Authorization: Basic $AUTH_HEADER" \
#   -d '{"agency_id": 10}'

# Process with auth
# curl -X POST http://localhost:5090/api/s3/process/ \
#   -H "Content-Type: application/json" \
#   -H "Authorization: Basic $AUTH_HEADER" \
#   -d '{"agency_id": 10, "dry_run": false}'

# -----------------------------
# Pretty-print JSON responses
# -----------------------------

# Analyze with jq formatting
curl -sS -X POST http://localhost:5090/api/s3/analyze/ \
  -H "Content-Type: application/json" \
  -d '{"agency_id": 10}' | jq .

# Process with jq formatting
curl -sS -X POST http://localhost:5090/api/s3/process/ \
  -H "Content-Type: application/json" \
  -d '{"agency_id": 10, "dry_run": true}' | jq .
