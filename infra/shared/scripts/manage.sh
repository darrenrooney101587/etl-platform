#!/usr/bin/env bash
set -euo pipefail

# manage.sh - Shared infrastructure manager
#
# Arguments:
#   $1: MODULE_NAME (e.g. file_processing, reporting_seeder)
#   $2: COMMAND (init|plan|apply|destroy|update-image|outputs)
#
# Environment Variables:
#   NAMESPACE (default: <module-name-with-hyphens>, e.g. file-processing)
#   DEPLOYMENT_NAME (default: <namespace>-sns for file_processing, else <namespace>)
#   CONTAINER_NAME (default: derived from module behavior)

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <module_name> {init|plan|apply|destroy|update-image|outputs}"
  exit 1
fi

MODULE_NAME="$1"
COMMAND="$2"

# Convert underscores to hyphens for K8s names
MODULE_K8S_NAME="${MODULE_NAME//_/-}"

# Default defaults
NAMESPACE="${NAMESPACE:-$MODULE_K8S_NAME}"

# Heuristic for DEPLOYMENT_NAME if not set
if [[ -z "${DEPLOYMENT_NAME:-}" ]]; then
  if [[ "$MODULE_NAME" == "file_processing" ]]; then
    DEPLOYMENT_NAME="file-processing-sns"
  elif [[ "$MODULE_NAME" == "observability" ]]; then
    DEPLOYMENT_NAME="observability-jobs"
  else
    DEPLOYMENT_NAME="$MODULE_K8S_NAME"
  fi
fi

# Heuristic for CONTAINER_NAME (name of the container in the pod spec to update)
# Usually matches the app label or deployment name, but sometimes varies
if [[ -z "${CONTAINER_NAME:-}" ]]; then
  if [[ "$MODULE_NAME" == "file_processing" ]]; then
    CONTAINER_NAME="sns-listener"
  elif [[ "$MODULE_NAME" == "reporting_seeder" ]]; then
    CONTAINER_NAME="reporting-seeder"
  elif [[ "$MODULE_NAME" == "observability" ]]; then
    CONTAINER_NAME="observability"
  else
    CONTAINER_NAME="$MODULE_K8S_NAME"
  fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
TF_DIR="${REPO_ROOT}/infra/${MODULE_NAME}/terraform"

echo "Module:     $MODULE_NAME"
echo "Command:    $COMMAND"
echo "Namespace:  $NAMESPACE"
echo "Deployment: $DEPLOYMENT_NAME"
echo "Container:  $CONTAINER_NAME"
echo "TF Dir:     $TF_DIR"

if [[ ! -d "$TF_DIR" ]]; then
  echo "Error: Terraform directory $TF_DIR does not exist."
  exit 1
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
  update-image)
    # Build and push using shared ecr_put.sh
    # We call the ecr_put.sh in the same directory as this script (infra/shared/scripts/)
    "$SCRIPT_DIR/ecr_put.sh" "$MODULE_NAME"

    IMAGE_URI=$(sed -n 's/container_image = "\([^"]*\)"/\1/p' "$TF_DIR/container_image.txt" || true)
    if [[ -z "$IMAGE_URI" ]]; then
      echo "Error: could not read image URI from $TF_DIR/container_image.txt"
      exit 1
    fi

    echo "Updating deployment $DEPLOYMENT_NAME in $NAMESPACE with $IMAGE_URI"

    # Fast path: if deployment exists, patch image via kubectl
    if kubectl -n "$NAMESPACE" get deployment "$DEPLOYMENT_NAME" --ignore-not-found >/dev/null 2>&1; then
      echo "Deployment exists — patching image..."
      kubectl -n "$NAMESPACE" set image deployment/"$DEPLOYMENT_NAME" "$CONTAINER_NAME=$IMAGE_URI"

      echo "Waiting for rollout..."
      kubectl -n "$NAMESPACE" rollout status deployment/"$DEPLOYMENT_NAME"

      echo "Restarting rollout to ensure update..."
      kubectl -n "$NAMESPACE" rollout restart deployment/"$DEPLOYMENT_NAME"
      kubectl -n "$NAMESPACE" rollout status deployment/"$DEPLOYMENT_NAME"
    else
      echo "Deployment not found in cluster — running terraform apply"
      terraform -chdir="$TF_DIR" init
      # Note: passing -var="image=..." assumes variables are set up this way in TF.
      # If TF relies on container_image.txt being present, simple apply is enough.
      # But some modules might use var input.
      terraform -chdir="$TF_DIR" apply -auto-approve -var="image=$IMAGE_URI"
    fi
    ;;
  outputs)
    terraform -chdir="$TF_DIR" output
    ;;
  *)
    echo "Unknown command: $COMMAND"
    exit 1
    ;;
esac
