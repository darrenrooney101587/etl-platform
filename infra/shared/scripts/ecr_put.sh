#!/bin/bash
set -euo pipefail

# ecr_put.sh
# Shared script to build and push docker images to ECR.
#
# Arguments:
#   $1: MODULE_NAME (e.g. pipeline_processing, reporting_seeder) - corresponds to packages/<name> and infra/<name>
#
# Environment Variables:
#   AWS_PROFILE (default: etl-playground)
#   AWS_REGION (default: us-gov-west-1)
#   ECR_REPO_NAME (default: converted from MODULE_NAME, e.g. pipeline_processing -> pipeline-processing)

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <module_name>"
  exit 1
fi

MODULE_NAME="$1"
# Convert underscores to hyphens for repo name default (e.g. pipeline_processing -> pipeline-processing)
DEFAULT_REPO_NAME="${MODULE_NAME//_/-}"

AWS_PROFILE="${AWS_PROFILE:-etl-playground}"
AWS_REGION="${AWS_REGION:-us-gov-west-1}"
ECR_REPO_NAME="${ECR_REPO_NAME:-$DEFAULT_REPO_NAME}"

# Determine repo root (assuming this script is in infra/shared/scripts/ or similar depth)
# We need to find the root of the git repo or project.
# Since this is "infra/shared/scripts/ecr_put.sh", roots is 3 levels up.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# Terraform dir for this module
TF_DIR="${REPO_ROOT}/infra/${MODULE_NAME}/terraform"

# Initial check for docker/ Dockerfile
DOCKERFILE_PATH="${REPO_ROOT}/docker/${DEFAULT_REPO_NAME}.Dockerfile"
BUILD_CONTEXT="${REPO_ROOT}"

# Fallback to package-level Dockerfile if repo-level is missing
if [[ ! -f "${DOCKERFILE_PATH}" ]]; then
  FALLBACK_DOCKERFILE="${REPO_ROOT}/packages/${MODULE_NAME}/${DEFAULT_REPO_NAME}.Dockerfile"
  # Also try without the prefix if that fails, though standard seems to be <name>.Dockerfile
  if [[ ! -f "${FALLBACK_DOCKERFILE}" ]]; then
     # Try just package root Dockerfile if naming varies?
     # But let's stick to the convention seen in pipeline_processing/reporting_seeder
     FALLBACK_DOCKERFILE="${REPO_ROOT}/packages/${MODULE_NAME}/${DEFAULT_REPO_NAME}.Dockerfile"
  fi

  if [[ -f "${FALLBACK_DOCKERFILE}" ]]; then
    DOCKERFILE_PATH="$FALLBACK_DOCKERFILE"
  fi
fi

echo "Module:        ${MODULE_NAME}"
echo "AWS Profile:   ${AWS_PROFILE}"
echo "AWS Region:    ${AWS_REGION}"
echo "ECR Repo:      ${ECR_REPO_NAME}"
echo "Repo root:     ${REPO_ROOT}"
echo "Dockerfile:    ${DOCKERFILE_PATH}"

if [[ ! -f "${DOCKERFILE_PATH}" ]]; then
  echo "Error: Dockerfile not found at ${DOCKERFILE_PATH}"
  echo "Checked repo-level: ${REPO_ROOT}/docker/${DEFAULT_REPO_NAME}.Dockerfile"
  echo "Checked pkg-level:  ${REPO_ROOT}/packages/${MODULE_NAME}/${DEFAULT_REPO_NAME}.Dockerfile"
  exit 1
fi

# Verify credentials
aws sts get-caller-identity --profile "${AWS_PROFILE}" >/dev/null

AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --profile "${AWS_PROFILE}")"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPO_NAME}:latest"

echo "AWS Account ID:   ${AWS_ACCOUNT_ID}"
echo "ECR Registry:     ${ECR_REGISTRY}"
echo "Image URI:        ${IMAGE_URI}"

# Ensure ECR repo exists
aws ecr describe-repositories \
  --repository-names "${ECR_REPO_NAME}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE}" >/dev/null 2>&1 \
|| aws ecr create-repository \
  --repository-name "${ECR_REPO_NAME}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE}" >/dev/null

# Login to ECR (required for push)
aws ecr get-login-password --region "${AWS_REGION}" --profile "${AWS_PROFILE}" \
| docker login --username AWS --password-stdin "${ECR_REGISTRY}" >/dev/null

# Ensure buildx builder exists (create if missing)
if ! docker buildx inspect fp-builder >/dev/null 2>&1; then
  docker buildx create --use --name fp-builder >/dev/null
else
  docker buildx use fp-builder >/dev/null
fi

# Build + push multi-arch image using repo root as build context
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "${IMAGE_URI}" \
  --push \
  -f "${DOCKERFILE_PATH}" \
  "${BUILD_CONTEXT}"

echo "Image pushed to: ${IMAGE_URI}"

# Write to TF_DIR so manage.sh can read it (and update deployment manifests if needed)
if [[ -d "${TF_DIR}" ]]; then
  mkdir -p "${TF_DIR}"
  echo "container_image = \"${IMAGE_URI}\"" > "${TF_DIR}/container_image.txt"
  echo "Wrote container_image to ${TF_DIR}/container_image.txt"
else
  echo "Warning: Terraform directory not found at ${TF_DIR}, could not write container_image.txt"
fi
