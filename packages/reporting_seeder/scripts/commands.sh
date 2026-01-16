#!/usr/bin/env bash
set -euo pipefail
./packages/reporting_seeder/scripts/build.sh
NETWORK=${NETWORK:-local_default}
JOB_NAME=${1:-hello_world}

docker run -d \
  --name reporting-seeder-main \
  --network "$NETWORK" \
  -v "$PWD":/app -w /app \
  --env-file packages/reporting_seeder/.env \
  -e PYTHONPATH=/app/packages \
  etl-reporting-seeder

#docker run --rm \
#  --network "$NETWORK" \
#  -v "$PWD":/app -w /app \
#  --env-file packages/reporting_seeder/.env \
#  -e PYTHONPATH=/app/packages \
#  etl-reporting-seeder \
#  python -m reporting_seeder.cli.main run "$JOB_NAME"
