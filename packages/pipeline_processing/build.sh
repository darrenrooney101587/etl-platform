#!/usr/bin/env bash
# packages/pipeline_processing/build.sh
# Helper to build the pipeline_processing Docker image from anywhere (uses repo root as build context).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PKG_NAME="pipeline_processing"
IMAGE_NAME="etl-pipeline-processing"
DASHED="${PKG_NAME//_/-}"
LOCAL_DOCKERFILE="$REPO_ROOT/packages/$PKG_NAME/${DASHED}.Dockerfile"
ALT_DOCKERFILE="$REPO_ROOT/docker/${DASHED}.Dockerfile"

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
