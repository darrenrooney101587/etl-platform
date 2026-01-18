#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
SHARED_SCRIPT="${REPO_ROOT}/infra/shared/scripts/manage.sh"
MODULE_NAME="pipeline_processing"
# Overrides for pipeline_processing specifics
export DEPLOYMENT_NAME="pipeline-processing-sns"
export CONTAINER_NAME="sns-listener"
"$SHARED_SCRIPT" "$MODULE_NAME" "$@"
