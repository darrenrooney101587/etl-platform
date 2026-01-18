#!/usr/bin/env bash
# packages/reporting_seeder/scripts/build.sh
# Build the reporting_seeder Docker image using the repo root as build context.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PKG_NAME="reporting_seeder"
IMAGE_NAME="etl-reporting-seeder"
DOCKERFILE_PATH="$REPO_ROOT/packages/$PKG_NAME/reporting-seeder.Dockerfile"

SHOW_HELP=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      SHOW_HELP=true
      shift
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$SHOW_HELP" == "true" ]]; then
  echo "Usage: $0"
  echo ""
  echo "Builds the local image '$IMAGE_NAME'."
  exit 0
fi

echo "Building image $IMAGE_NAME using Dockerfile: $DOCKERFILE_PATH with context: $REPO_ROOT"
docker build -t "$IMAGE_NAME" -f "$DOCKERFILE_PATH" "$REPO_ROOT"

echo "Build complete: $IMAGE_NAME"

