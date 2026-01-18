#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
SHARED_SCRIPT="${REPO_ROOT}/infra/shared/scripts/manage.sh"
MODULE_NAME="observability"
export DEPLOYMENT_NAME="observability-jobs"
export CONTAINER_NAME="observability"
"$SHARED_SCRIPT" "$MODULE_NAME" "$@"
