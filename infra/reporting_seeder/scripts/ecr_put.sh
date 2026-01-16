#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
SHARED_SCRIPT="${REPO_ROOT}/infra/shared/scripts/ecr_put.sh"
MODULE_NAME="reporting_seeder"
"$SHARED_SCRIPT" "$MODULE_NAME" "$@"
