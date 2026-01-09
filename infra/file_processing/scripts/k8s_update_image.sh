#!/usr/bin/env bash
set -euo pipefail

KUBECONFIG_PATH="${KUBECONFIG:-}"
NAMESPACE="${NAMESPACE:-file-processing}"
IMAGE="${IMAGE:-}"

if [[ -z "$IMAGE" ]]; then
  echo "Usage: IMAGE=registry/image:tag $0"
  exit 2
fi

kubectl_cmd=(kubectl)
if [[ -n "$KUBECONFIG_PATH" ]]; then
  kubectl_cmd+=(--kubeconfig "$KUBECONFIG_PATH")
fi

DEPLOYMENT_NAME="file-processing-sns"
CONTAINER_NAME="sns-listener"

echo "Updating deployment $DEPLOYMENT_NAME in namespace $NAMESPACE to image $IMAGE"
"${kubectl_cmd[@]}" -n "$NAMESPACE" set image deployment/$DEPLOYMENT_NAME "$CONTAINER_NAME"="$IMAGE" --record
"${kubectl_cmd[@]}" -n "$NAMESPACE" rollout status deployment/$DEPLOYMENT_NAME

echo "Image update complete."
