#!/usr/bin/env bash
# Wrapper for LocalStack setup specific to airflow_control_plane
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
SHARED_SCRIPT="${REPO_ROOT}/infra/local/scripts/setup_localstack.sh"
"$SHARED_SCRIPT" "airflow_control_plane" "$@"
