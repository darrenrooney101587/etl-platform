#!/usr/bin/env bash
set -euo pipefail

# Dev entrypoint that enforces running the package console script (CLI) only.
# This prevents running arbitrary subprocesses inside the container and
# provides a guardrail: the container will run `data-pipeline` with any
# provided args after ensuring dependencies are installed.

SKIP_INSTALL=${SKIP_INSTALL:-}

# Ensure poetry is available (the Dockerfile normally installs it during build)
if ! command -v poetry >/dev/null 2>&1; then
  echo "[entrypoint] poetry not found, installing poetry via pip..."
  pip install poetry --quiet
fi

if [ -z "${SKIP_INSTALL}" ]; then
  # Check if package is importable
  python - <<'PY' >/dev/null 2>&1 || INSTALL_ERR=$?
try:
    import data_pipeline  # noqa: F401
except Exception:
    raise SystemExit(2)
else:
    raise SystemExit(0)
PY
  if [ "${?}" -ne 0 ] || [ -n "${INSTALL_ERR-}" ]; then
    echo "[entrypoint] data_pipeline not importable; running poetry install (dev)..."
    poetry config virtualenvs.create false || true
    poetry install --no-root --no-interaction --no-ansi
  else
    echo "[entrypoint] data_pipeline importable; skipping install"
  fi
else
  echo "[entrypoint] SKIP_INSTALL set; skipping poetry install"
fi

# Enforce CLI usage: always exec the console script 'data-pipeline' with provided args
# Users who want a shell should override the entrypoint: --entrypoint /bin/bash

echo "[entrypoint] Executing canonical CLI: data-pipeline $*"
exec data-pipeline "$@"
