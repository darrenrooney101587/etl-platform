#!/usr/bin/env bash
# etl_core/scripts/stage_schema.sh
# Stage the sibling etl-database-schema into .local/etl-database-schema
# This script assumes the etl-database-schema repository is checked out as a sibling
# directory next to this repository (../etl-database-schema).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SRC_PATH="${REPO_ROOT}/../etl-database-schema"
STAGING_DIR="${REPO_ROOT}/.local/etl-database-schema"

if [[ ! -d "$SRC_PATH" ]]; then
  echo "Missing expected sibling etl-database-schema at: $SRC_PATH" >&2
  echo "Please clone or checkout the etl-database-schema repo as a sibling of this repo:" >&2
  echo "  git clone <url> $SRC_PATH" >&2
  exit 1
fi

mkdir -p "${REPO_ROOT}/.local"
rm -rf "$STAGING_DIR"

if command -v rsync >/dev/null 2>&1; then
  echo "Staging from $SRC_PATH -> $STAGING_DIR using rsync..."
  rsync -a --delete \
    --exclude ".git" \
    --exclude "__pycache__" \
    --exclude ".ruff_cache" \
    "$SRC_PATH/" "$STAGING_DIR/"
else
  echo "rsync not found; falling back to cp -R"
  cp -R "$SRC_PATH" "$STAGING_DIR"
  rm -rf "$STAGING_DIR/.git" || true
fi

echo "Staged etl-database-schema into: $STAGING_DIR"
exit 0
