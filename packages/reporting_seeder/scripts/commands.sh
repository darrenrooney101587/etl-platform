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

# Run a one-shot hello_world job locally (uncomment to execute)
# docker run --rm \
#   --network "$NETWORK" \
#   -v "$PWD":/app -w /app \
#   --env-file packages/reporting_seeder/.env \
#   -e PYTHONPATH=/app/packages \
#   etl-reporting-seeder \
#   python -m reporting_seeder.cli.main run "$JOB_NAME"

# Example Kubernetes on-demand Job commands (commented out)
# Use the manifest (recommended): this job manifest will run the packaged CLI
# and is configured to read env from ConfigMap/Secret in the cluster:
#
# kubectl apply -f infra/reporting_seeder/k8s/reporting-seeder-job.yaml
#
# Or create a one-off Job directly (substitute your image/registry and namespace):
#
# kubectl create job reporting-seeder-run-once \
#   --image=270022076279.dkr.ecr.us-gov-west-1.amazonaws.com/reporting-seeder:latest \
#   --namespace=reporting-seeder -- python -m reporting_seeder.cli.main run refresh_all
#
# Note: when creating jobs directly you should also ensure required env (DB_HOST, DB_PASSWORD,
# DJANGO_SETTINGS_MODULE, etc.) are provided via a ConfigMap/Secret or inline `--env` flags.
