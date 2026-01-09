#!/usr/bin/env bash
set -euo pipefail

# manage_cluster.sh - File Processing infrastructure lifecycle
#
# Responsibilities in this stack:
# - Build/push image to ECR
# - Provision and update the file_processing EKS cluster + Kubernetes resources
# - Provision SNS topic and optional S3 bucket notifications
#
# This script intentionally does NOT create shared AWS networking primitives.
# Run infra/foundation_network/scripts/manage.sh first.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
COMMAND="${1:-help}"

function print_usage() {
  echo "Usage: $0 {init|update|teardown}"
  echo ""
  echo "Prerequisite: run the foundation stack first:"
  echo "  (cd infra/foundation_network && ./scripts/manage.sh apply)"
  echo ""
  echo "Commands:"
  echo "  init      Build image, push to ECR, terraform apply (creates EKS + K8s + SNS wiring)"
  echo "  update    Build image, push to ECR, terraform apply (updates Deployment image + wiring)"
  echo "  teardown  terraform destroy (destroys EKS + K8s + SNS wiring)"
}

if [[ "$COMMAND" == "help" || "$COMMAND" == "-h" ]]; then
  print_usage
  exit 0
fi

function get_image_uri() {
  local ci_file="$INFRA_DIR/container_image.txt"
  if [[ -f "$ci_file" ]]; then
    local uri
    uri=$(sed -n 's/container_image = "\([^"]*\)"/\1/p' "$ci_file")
    echo "$uri"
  else
    echo ""
  fi
}

if [[ "$COMMAND" == "init" || "$COMMAND" == "update" ]]; then
  echo "=== [1/3] Building and Pushing Image ==="
  "$SCRIPT_DIR/ecr_put.sh"

  IMAGE_URI=$(get_image_uri)
  if [[ -z "$IMAGE_URI" ]]; then
    echo "Error: Could not determine image URI from ecr_put.sh output."
    exit 1
  fi
  echo "Image: $IMAGE_URI"

  echo "=== [2/3] Initializing Terraform (file_processing stack) ==="
  cd "$INFRA_DIR"
  terraform init

  echo "=== [3/3] Applying Infrastructure ==="
  terraform apply -var="image=$IMAGE_URI" -auto-approve

  echo "Done."
  exit 0
fi

if [[ "$COMMAND" == "teardown" ]]; then
  echo "=== Teardown file_processing infrastructure ==="
  cd "$INFRA_DIR"
  terraform init
  terraform destroy -auto-approve
  echo "Teardown complete."
  exit 0
fi

echo "Unknown command: $COMMAND"
print_usage
exit 1
