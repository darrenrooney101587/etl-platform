#!/bin/bash
set -e

#echo "[ENTRYPOINT] Testing SSH connection to GitLab..."
#if ssh -T git@gitlab.dev-benchmarkanalytics.com 2>&1 | grep -q "Welcome to GitLab"; then
#  echo "[ENTRYPOINT] SSH authentication successful."
#else
#  echo "[ERROR] SSH authentication to GitLab failed!"
#  exit 1
#fi

echo "[ENTRYPOINT] Installing project dependencies..."
poetry install --no-root || { echo "[ERROR] Poetry install failed"; exit 1; }

echo "[ENTRYPOINT] Ready. Use 'poetry run data-pipeline-get-s3-files --help' to run the CLI."
exec "$@"
