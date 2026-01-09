#!/usr/bin/env bash
set -euo pipefail

# manage.sh - file_processing
#
# This stack provisions a dedicated EKS cluster plus SNS wiring and Kubernetes resources.
# It depends on the VPC/subnets created by infra/foundation_network.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
STACK_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMMAND="${1:-help}"

function print_usage() {
  echo "Usage: $0 {init|plan|apply|destroy|update-image|outputs}"
  echo ""
  echo "Commands:"
  echo "  init         - terraform init"
  echo "  plan         - terraform plan"
  echo "  apply        - terraform apply -auto-approve"
  echo "  destroy      - terraform destroy -auto-approve"
  echo "  update-image - build/push to ECR then terraform apply with the new image"
  echo "  outputs      - terraform output"
  echo ""
  echo "Prereq: foundation_network applied and its terraform.tfstate exists."
}

if [[ "$COMMAND" == "help" || "$COMMAND" == "-h" ]]; then
  print_usage
  exit 0
fi

cd "$STACK_DIR"

case "$COMMAND" in
  init)
    terraform init
    ;;
  plan)
    terraform init
    terraform plan
    ;;
  apply)
    terraform init
    terraform apply -auto-approve
    ;;
  destroy)``
    terraform init
    terraform destroy -auto-approve
    ;;
  update-image)
    terraform init
    ./scripts/ecr_put.sh
    IMAGE_URI=$(sed -n 's/container_image = "\([^"]*\)"/\1/p' container_image.txt || true)
    if [[ -z "$IMAGE_URI" ]]; then
      echo "Error: could not read image URI from container_image.txt"
      exit 1
    fi
    terraform apply -auto-approve -var="image=$IMAGE_URI"
    ;;
  outputs)
    terraform output
    ;;
  *)
    echo "Unknown command: $COMMAND"
    print_usage
    exit 1
    ;;
esac
