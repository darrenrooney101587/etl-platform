#!/usr/bin/env bash
set -euo pipefail

# manage.sh - foundation_network
#
# This stack is intended to be applied once per environment.
# It creates shared network primitives (VPC/subnets/IGW/NAT/routes).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TF_DIR="${STACK_DIR}/terraform"
COMMAND="${1:-help}"

function print_usage() {
  echo "Usage: $0 {init|apply|plan|destroy|output}"
  echo ""
  echo "Commands:"
  echo "  init     - terraform init"
  echo "  plan     - terraform plan"
  echo "  apply    - terraform apply -auto-approve"
  echo "  destroy  - terraform destroy -auto-approve (danger)"
  echo "  output   - terraform output"
}

if [[ "$COMMAND" == "help" || "$COMMAND" == "-h" ]]; then
  print_usage
  exit 0
fi

case "$COMMAND" in
  init)
    terraform -chdir="$TF_DIR" init
    ;;
  plan)
    terraform -chdir="$TF_DIR" init
    terraform -chdir="$TF_DIR" plan
    ;;
  apply)
    terraform -chdir="$TF_DIR" init
    terraform -chdir="$TF_DIR" apply -auto-approve
    ;;
  destroy)
    terraform -chdir="$TF_DIR" init
    terraform -chdir="$TF_DIR" destroy -auto-approve
    ;;
  output)
    terraform -chdir="$TF_DIR" output
    ;;
  *)
    echo "Unknown command: $COMMAND"
    print_usage
    exit 1
    ;;
esac
