#!/usr/bin/env bash
set -euo pipefail

KUBECONFIG_PATH="${KUBECONFIG:-}"
NAMESPACE="${NAMESPACE:-file-processing}"
REMOVE_NAMESPACE="${REMOVE_NAMESPACE:-false}"
MANIFEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/k8s"

kubectl_cmd=(kubectl)
if [[ -n "$KUBECONFIG_PATH" ]]; then
  kubectl_cmd+=(--kubeconfig "$KUBECONFIG_PATH")
fi

echo "Deleting manifests from: $MANIFEST_DIR in namespace $NAMESPACE"
"${kubectl_cmd[@]}" delete -f "$MANIFEST_DIR" --namespace "$NAMESPACE" --ignore-not-found

if [[ "$REMOVE_NAMESPACE" == "true" ]]; then
  echo "Removing namespace $NAMESPACE"
  "${kubectl_cmd[@]}" delete namespace "$NAMESPACE" --ignore-not-found
fi

echo "Teardown complete."
