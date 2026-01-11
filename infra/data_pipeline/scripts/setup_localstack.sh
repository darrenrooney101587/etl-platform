#!/usr/bin/env bash
set -euo pipefail

# Wrapper for LocalStack setup for the data_pipeline perspective.
# Usage: ./setup_localstack.sh [listener_host] [listener_port]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/../local/scripts/setup_localstack.sh" "${1:-host.docker.internal}" "${2:-8080}" data_pipeline
