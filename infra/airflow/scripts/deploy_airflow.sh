#!/usr/bin/env bash
# Deploy Airflow to Kubernetes using Helm
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="${SCRIPT_DIR}/../k8s"
ENVIRONMENT="${ENVIRONMENT:-dev}"
NAMESPACE="airflow"
RELEASE_NAME="airflow"

usage() {
  cat <<EOF
Usage: $0 <command> [args]

Commands:
  install              Install Airflow using Helm
  upgrade              Upgrade Airflow release
  uninstall            Uninstall Airflow
  status               Check Airflow release status
  logs                 Show scheduler and dag-sync logs

Environment variables:
  ENVIRONMENT          Environment name (dev, staging, prod) [default: dev]
  DAG_BUCKET           S3 bucket name for DAGs (required)
  AWS_REGION           AWS region [default: us-gov-west-1]
  AIRFLOW_CHART_VERSION Airflow Helm chart version [default: 1.12.0]

Examples:
  # Install
  ENVIRONMENT=dev DAG_BUCKET=etl-airflow-dags-dev $0 install

  # Upgrade
  ENVIRONMENT=dev DAG_BUCKET=etl-airflow-dags-dev $0 upgrade

  # Check status
  $0 status
EOF
  exit 1
}

case "${1:-}" in
  install)
    if [[ -z "${DAG_BUCKET:-}" ]]; then
      echo "ERROR: DAG_BUCKET is required"
      exit 1
    fi
    
    # Create namespace
    kubectl apply -f "${K8S_DIR}/namespaces.yaml"
    
    # Create ConfigMap
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: airflow-config
  namespace: ${NAMESPACE}
data:
  ENVIRONMENT: "${ENVIRONMENT}"
  AWS_REGION: "${AWS_REGION:-us-gov-west-1}"
  DAG_BUCKET: "${DAG_BUCKET}"
EOF
    
    # Add Airflow Helm repo
    helm repo add apache-airflow https://airflow.apache.org
    helm repo update
    
    # Install Airflow
    helm install "${RELEASE_NAME}" apache-airflow/airflow \
      --namespace "${NAMESPACE}" \
      --values "${K8S_DIR}/airflow-values.yaml" \
      --version "${AIRFLOW_CHART_VERSION:-1.12.0}" \
      --wait
    
    echo "Airflow installed successfully!"
    ;;
  
  upgrade)
    if [[ -z "${DAG_BUCKET:-}" ]]; then
      echo "ERROR: DAG_BUCKET is required"
      exit 1
    fi
    
    # Update ConfigMap
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: airflow-config
  namespace: ${NAMESPACE}
data:
  ENVIRONMENT: "${ENVIRONMENT}"
  AWS_REGION: "${AWS_REGION:-us-gov-west-1}"
  DAG_BUCKET: "${DAG_BUCKET}"
EOF
    
    # Upgrade Airflow
    helm upgrade "${RELEASE_NAME}" apache-airflow/airflow \
      --namespace "${NAMESPACE}" \
      --values "${K8S_DIR}/airflow-values.yaml" \
      --version "${AIRFLOW_CHART_VERSION:-1.12.0}" \
      --wait
    
    echo "Airflow upgraded successfully!"
    ;;
  
  uninstall)
    helm uninstall "${RELEASE_NAME}" --namespace "${NAMESPACE}" || true
    kubectl delete namespace "${NAMESPACE}" --ignore-not-found=true
    kubectl delete namespace "etl-jobs" --ignore-not-found=true
    ;;
  
  status)
    helm status "${RELEASE_NAME}" --namespace "${NAMESPACE}"
    kubectl get pods -n "${NAMESPACE}"
    ;;
  
  logs)
    echo "=== Scheduler logs ==="
    kubectl logs -n "${NAMESPACE}" -l component=scheduler --tail=50
    echo ""
    echo "=== DAG sync sidecar logs ==="
    kubectl logs -n "${NAMESPACE}" -l component=scheduler -c dag-sync --tail=50
    ;;
  
  *)
    usage
    ;;
esac
