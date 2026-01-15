#!/usr/bin/env bash
# packages/file_processing/scripts/build.sh
# Build the file_processing Docker image using the repo root as build context.
#
# Local dev (recommended): keep a checkout of etl-database-schema next to this repo at:
#   ../etl-database-schema
#
# You can also pass an explicit path:
#   ./packages/file_processing/scripts/build.sh --schema-path /abs/path/to/etl-database-schema
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PKG_NAME="file_processing"
IMAGE_NAME="etl-file-processing"
DASHED="${PKG_NAME//_/-}"
LOCAL_DOCKERFILE="$REPO_ROOT/packages/$PKG_NAME/file-processing.Dockerfile"
ALT_DOCKERFILE="$REPO_ROOT/docker/${DASHED}.Dockerfile"

DEFAULT_SCHEMA_PATH="${REPO_ROOT}/../etl-database-schema"
SCHEMA_PATH=""
STAGING_DIR="${REPO_ROOT}/.local/etl-database-schema"

SHOW_HELP=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      SHOW_HELP=true
      shift
      ;;
    --schema-path)
      if [[ -z "${2:-}" ]]; then
        echo "--schema-path requires an argument" >&2
        exit 1
      fi
      SCHEMA_PATH="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$SHOW_HELP" == "true" ]]; then
  echo "Usage: $0 [--schema-path /abs/path/to/etl-database-schema]"
  echo ""
  echo "Builds the local image '$IMAGE_NAME' after staging etl-database-schema into .local/etl-database-schema."
  exit 0
fi

if [[ -z "$SCHEMA_PATH" ]]; then
  SCHEMA_PATH="$DEFAULT_SCHEMA_PATH"
fi

if [[ ! -d "$SCHEMA_PATH" ]]; then
  echo "Missing schema checkout at: $SCHEMA_PATH" >&2
  echo "Clone it next to the repo root or pass --schema-path." >&2
  echo "Example: git clone git@gitlab.dev-benchmarkanalytics.com:etl/etl-database-schema.git ../etl-database-schema" >&2
  exit 1
fi

mkdir -p "${REPO_ROOT}/.local"
rm -rf "${STAGING_DIR}"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude ".git" \
    --exclude "__pycache__" \
    --exclude ".ruff_cache" \
    "${SCHEMA_PATH}/" "${STAGING_DIR}/"
else
  cp -R "$SCHEMA_PATH" "$STAGING_DIR"
  rm -rf "${STAGING_DIR}/.git" || true
fi

echo "Staged etl-database-schema into: $STAGING_DIR"

if [ -f "$LOCAL_DOCKERFILE" ]; then
  DOCKERFILE_PATH="$LOCAL_DOCKERFILE"
elif [ -f "$ALT_DOCKERFILE" ]; then
  DOCKERFILE_PATH="$ALT_DOCKERFILE"
else
  echo "No Dockerfile found for package $PKG_NAME (looked for $LOCAL_DOCKERFILE and $ALT_DOCKERFILE)" >&2
  exit 1
fi

echo "Building image $IMAGE_NAME using Dockerfile: $DOCKERFILE_PATH with context: $REPO_ROOT"

docker build -t "$IMAGE_NAME" -f "$DOCKERFILE_PATH" "$REPO_ROOT"

echo "Build complete: $IMAGE_NAME"
