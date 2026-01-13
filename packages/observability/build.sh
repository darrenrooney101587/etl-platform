#!/usr/bin/env bash
# packages/observability/build.sh
# Helper to build the observability image from anywhere (uses repo root as build context).
set -euo pipefail

# Resolve repo root (two levels up from this script)
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DOCKERFILE_PATH="$REPO_ROOT/packages/observability/observability.Dockerfile"
IMAGE_NAME="etl-observability"

echo "Building image $IMAGE_NAME using Dockerfile: $DOCKERFILE_PATH with context: $REPO_ROOT"

docker build -t "$IMAGE_NAME" -f "$DOCKERFILE_PATH" "$REPO_ROOT"

echo "Build complete: $IMAGE_NAME"
