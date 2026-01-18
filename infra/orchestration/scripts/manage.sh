#!/usr/bin/env bash
# Terraform lifecycle helper for Airflow infrastructure
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/../terraform"
ENVIRONMENT="${ENVIRONMENT:-dev}"

usage() {
  cat <<EOF
Usage: $0 <command> [args]

Commands:
  init                 Initialize Terraform
  plan                 Show execution plan
  apply                Apply changes
  destroy              Destroy infrastructure
  outputs              Show Terraform outputs
  validate             Validate Terraform configuration

Environment variables:
  ENVIRONMENT          Environment name (dev, staging, prod) [default: dev]
  VPC_ID              VPC ID (required for apply)
  SUBNET_IDS          Comma-separated private subnet IDs (required for apply)
  EKS_CLUSTER_NAME    EKS cluster name (required for apply)
  AWS_REGION          AWS region [default: us-gov-west-1]

Examples:
  # Initialize
  $0 init

  # Plan changes
  ENVIRONMENT=dev VPC_ID=vpc-xxx SUBNET_IDS=subnet-a,subnet-b EKS_CLUSTER_NAME=my-cluster $0 plan

  # Apply changes
  ENVIRONMENT=dev VPC_ID=vpc-xxx SUBNET_IDS=subnet-a,subnet-b EKS_CLUSTER_NAME=my-cluster $0 apply

  # Show outputs
  $0 outputs
EOF
  exit 1
}

validate_env() {
  local cmd="$1"
  
  if [[ "$cmd" == "apply" ]] || [[ "$cmd" == "plan" ]]; then
    if [[ -z "${VPC_ID:-}" ]]; then
      echo "ERROR: VPC_ID is required for $cmd"
      exit 1
    fi
    if [[ -z "${SUBNET_IDS:-}" ]]; then
      echo "ERROR: SUBNET_IDS is required for $cmd"
      exit 1
    fi
    if [[ -z "${EKS_CLUSTER_NAME:-}" ]]; then
      echo "ERROR: EKS_CLUSTER_NAME is required for $cmd"
      exit 1
    fi
  fi
}

cd "$TERRAFORM_DIR"

COMMAND="${1:-}"
case "$COMMAND" in
  init)
    terraform init
    ;;
  
  plan)
    validate_env "plan"
    terraform plan \
      -var="environment=${ENVIRONMENT}" \
      -var="vpc_id=${VPC_ID}" \
      -var="private_subnet_ids=[\"$(echo "$SUBNET_IDS" | sed 's/,/","/g')\"]" \
      -var="eks_cluster_name=${EKS_CLUSTER_NAME}" \
      -var="aws_region=${AWS_REGION:-us-gov-west-1}"
    ;;
  
  apply)
    validate_env "apply"
    terraform apply \
      -var="environment=${ENVIRONMENT}" \
      -var="vpc_id=${VPC_ID}" \
      -var="private_subnet_ids=[\"$(echo "$SUBNET_IDS" | sed 's/,/","/g')\"]" \
      -var="eks_cluster_name=${EKS_CLUSTER_NAME}" \
      -var="aws_region=${AWS_REGION:-us-gov-west-1}"
    ;;
  
  destroy)
    terraform destroy \
      -var="environment=${ENVIRONMENT}" \
      -var="vpc_id=${VPC_ID:-vpc-dummy}" \
      -var="private_subnet_ids=[\"subnet-dummy\"]" \
      -var="eks_cluster_name=${EKS_CLUSTER_NAME:-cluster-dummy}" \
      -var="aws_region=${AWS_REGION:-us-gov-west-1}"
    ;;
  
  outputs)
    terraform output
    ;;
  
  validate)
    terraform validate
    ;;
  
  *)
    usage
    ;;
esac
