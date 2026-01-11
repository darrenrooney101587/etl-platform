#!/usr/bin/env bash
set -euo pipefail

# Build and push reporting-seeder image to ECR based on terraform outputs
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TF_DIR="${STACK_DIR}/terraform"

# Read image uri target from terraform outputs file if present
IMAGE_URI=$(sed -n 's/container_image = "\([^"]*\)"/\1/p' "$TF_DIR/container_image.txt" || true)
if [[ -z "$IMAGE_URI" ]]; then
  echo "container_image.txt missing or empty; ensure terraform outputs are generated"
  exit 1
fi

echo "Building image $IMAGE_URI"

docker build -f "$STACK_DIR/../../docker/reporting-seeder.Dockerfile" -t "$IMAGE_URI" "$STACK_DIR/../.."
docker push "$IMAGE_URI"
