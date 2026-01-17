#!/usr/bin/env bash
set -euo pipefail

# Build the image first
./packages/reporting_seeder/scripts/build.sh

NETWORK=${NETWORK:-local_default}
JOB_NAME=${1:-hello_world}

# Check if arguments were provided (so we can shift $1 safely)
if [ "$#" -ge 1 ]; then
    shift
fi

# Run the job in a disposable container (one-shot)
# This matches how we run jobs in k8s (a fresh container per job invocation)
docker run --rm \
  --network "$NETWORK" \
  -v "$PWD":/app -w /app \
  --env-file packages/reporting_seeder/.env \
  -e PYTHONPATH=/app/packages \
  etl-reporting-seeder \
  python -m reporting_seeder.cli.main run "$JOB_NAME" "$@"
