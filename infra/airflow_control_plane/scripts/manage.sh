#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
SHARED_SCRIPT="${REPO_ROOT}/infra/shared/scripts/manage.sh"
MODULE_NAME="airflow_control_plane"
# Overrides for airflow_control_plane specifics
export DEPLOYMENT_NAME="airflow-scheduler"
export CONTAINER_NAME="airflow-scheduler"
"$SHARED_SCRIPT" "$MODULE_NAME" "$@"
