#!/usr/bin/env bash
set -euo pipefail

PORT=${1:-8080}
ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"
if [ -f "$ENV_FILE" ]; then
  echo "Loading environment from $ENV_FILE"
  set -a
  source "$ENV_FILE"
  set +a
fi

export PORT=${PORT:-${PORT}}
python -m file_processing.cli.sns_main
