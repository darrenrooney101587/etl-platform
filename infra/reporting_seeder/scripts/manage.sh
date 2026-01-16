#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
SHARED_SCRIPT="${REPO_ROOT}/infra/shared/scripts/manage.sh"
MODULE_NAME="reporting_seeder"
# Optional overrides if defaults in shared script aren't enough
# export DEPLOYMENT_NAME="reporting-seeder"
# export NAMESPACE="reporting-seeder"
# export CONTAINER_NAME="reporting-seeder"
"$SHARED_SCRIPT" "$MODULE_NAME" "$@"
