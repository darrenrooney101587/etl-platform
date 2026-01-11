#!/usr/bin/env bash
set -euo pipefail

# Run the SNS listener locally in the foreground for development.
# Usage: ./run_local_listener.sh [PORT]
PORT=${1:-8080}

# If a .env file exists in the package, export its values into the environment
ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"
if [ -f "$ENV_FILE" ]; then
  echo "Loading environment from $ENV_FILE"
  # Export all defined variables from the .env into the environment
  # shellcheck disable=SC1090
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

# Allow overriding PORT via env too, but prefer CLI arg
export PORT=${PORT:-${PORT}}

# Activate poetry venv if available (optional)
# source $(poetry env info -p)/bin/activate 2>/dev/null || true

# Run the SNS listener module (it reads PORT and DB_* / DATABASE_URL from env)
python -m file_processing.cli.sns_main
