#!/usr/bin/env bash
set -euo pipefail

# manage.sh - foundation_network
#
# This stack is intended to be applied once per environment.
# It creates shared network primitives (VPC/subnets/IGW/NAT/routes).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
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
  destroy)
    terraform init
    terraform destroy -auto-approve
    ;;
  output)
    terraform output
    ;;
  *)
    echo "Unknown command: $COMMAND"
    print_usage
    exit 1
    ;;
esac
