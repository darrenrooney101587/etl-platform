#!/usr/bin/env bash
# LocalStack setup for local Airflow DAG testing
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/../../.."

# Delegate to the shared LocalStack setup
"${ROOT_DIR}/infra/local/scripts/setup_localstack.sh" "$@"

# Additional Airflow-specific LocalStack setup
setup_airflow_localstack() {
  echo "Setting up Airflow DAG bucket in LocalStack..."
  
  ENVIRONMENT="${ENVIRONMENT:-dev}"
  DAG_BUCKET="etl-airflow-dags-${ENVIRONMENT}"
  
  # Create DAG bucket
  awslocal s3 mb "s3://${DAG_BUCKET}" 2>/dev/null || echo "Bucket already exists"
  
  # Create environment prefix
  awslocal s3api put-object --bucket "${DAG_BUCKET}" --key "${ENVIRONMENT}/" || true
  
  echo "LocalStack setup complete."
  echo "DAG Bucket: s3://${DAG_BUCKET}/${ENVIRONMENT}/"
}

case "${1:-setup}" in
  setup)
    setup_airflow_localstack
    ;;
  *)
    echo "Unknown command: $1"
    exit 1
    ;;
esac
