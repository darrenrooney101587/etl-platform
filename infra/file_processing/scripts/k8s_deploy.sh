#!/usr/bin/env bash
set -euo pipefail

# Deploy manifests in infra/file_processing/k8s to the target cluster
# Environment variables:
#  KUBECONFIG - path to kubeconfig (optional; falls back to default)
#  NAMESPACE  - target namespace (default: file-processing)
#  IMAGE      - container image to use (optional; if provided the script updates the deployment image after apply)

KUBECONFIG_PATH="${KUBECONFIG:-}"
NAMESPACE="${NAMESPACE:-file-processing}"
IMAGE="${IMAGE:-}"
MANIFEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/k8s"

kubectl_cmd=(kubectl)
if [[ -n "$KUBECONFIG_PATH" ]]; then
  kubectl_cmd+=(--kubeconfig "$KUBECONFIG_PATH")
fi

echo "Using kubeconfig: ${KUBECONFIG_PATH:-default}"
echo "Target namespace: ${NAMESPACE}"

# Ensure namespace exists
if ! "${kubectl_cmd[@]}" get namespace "$NAMESPACE" >/dev/null 2>&1; then
  echo "Creating namespace: $NAMESPACE"
  "${kubectl_cmd[@]}" create namespace "$NAMESPACE"
else
  echo "Namespace $NAMESPACE already exists"
fi

# Apply manifests
echo "Applying manifests from: $MANIFEST_DIR"
"${kubectl_cmd[@]}" apply -f "$MANIFEST_DIR" --namespace "$NAMESPACE"

# If IMAGE provided, update the deployment image
if [[ -n "$IMAGE" ]]; then
  DEPLOYMENT_NAME="file-processing-sns"
  CONTAINER_NAME="sns-listener"
  echo "Updating deployment $DEPLOYMENT_NAME image to $IMAGE"
  "${kubectl_cmd[@]}" -n "$NAMESPACE" set image deployment/$DEPLOYMENT_NAME "$CONTAINER_NAME"="$IMAGE" --record
  echo "Waiting for rollout to finish..."
  "${kubectl_cmd[@]}" -n "$NAMESPACE" rollout status deployment/$DEPLOYMENT_NAME
fi

echo "Deployment complete."
