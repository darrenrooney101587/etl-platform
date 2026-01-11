#!/bin/bash
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-etl-playground}"
AWS_REGION="${AWS_REGION:-us-gov-west-1}"
ECR_REPO_NAME="file-processing"

# Determine repo root (two levels up from infra/file_processing/scripts)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
# Terraform dir for this stack
TF_DIR="${REPO_ROOT}/infra/file_processing/terraform"
DOCKERFILE_PATH="${REPO_ROOT}/docker/file-processing.Dockerfile"
BUILD_CONTEXT="${REPO_ROOT}"

echo "Using AWS Profile: ${AWS_PROFILE}"
echo "Using AWS Region:  ${AWS_REGION}"

echo "Repo root: ${REPO_ROOT}"
echo "Dockerfile: ${DOCKERFILE_PATH}"

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
# Write to TF_DIR so manage.sh can read it
mkdir -p "${TF_DIR}"
echo "container_image = \"${IMAGE_URI}\"" > "${TF_DIR}/container_image.txt"
