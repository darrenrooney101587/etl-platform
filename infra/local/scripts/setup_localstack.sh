#!/usr/bin/env bash
set -euo pipefail

# setup_localstack.sh
# Bring up LocalStack and create SNS topic, S3 bucket, and subscribe the HTTP endpoint.
# This script is perspective-aware for monorepo layouts: file_processing, data_pipeline, observability.

# Usage: ./setup_localstack.sh <listener_host> <listener_port> [perspective]
# Example: ./setup_localstack.sh host.docker.internal 8080 file_processing

LISTENER_HOST=${1:-host.docker.internal}
LISTENER_PORT=${2:-8080}
PERSPECTIVE=${3:-file_processing}
AWS_REGION=${AWS_REGION:-us-east-1}

# Prefer HTTPS edge, fall back to HTTP if necessary
EDGE_URLS=("https://localhost:4566" "http://localhost:4566")

# Normalize perspective -> use allowed set
case "$PERSPECTIVE" in
  file_processing|data_pipeline|observability)
    ;;
  *)
    echo "Unknown perspective: $PERSPECTIVE"
    echo "Valid perspectives: file_processing, data_pipeline, observability"
    exit 1
    ;;
esac

# Sanitize perspective for AWS resource names: lowercase, only a-z0-9 and hyphens
PERSPECTIVE_SAFE=$(echo "$PERSPECTIVE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/-\+/-/g' | sed 's/^-//; s/-$//')

echo "Starting LocalStack (if not already)..."
# docker-compose.yml lives in infra/local/docker/docker-compose.yml relative to this script
DC_FILE="$(cd "$(dirname "$0")/.." && pwd)/docker/docker-compose.yml"
echo "Using docker-compose file: $DC_FILE"
docker-compose -f "$DC_FILE" up -d || true

# Wait for LocalStack edge port to be reachable (try https then http)
HEALTH_OK=0
for EDGE_URL in "${EDGE_URLS[@]}"; do
  for i in {1..8}; do
    echo "Checking LocalStack edge at $EDGE_URL (attempt $i)..."
    if curl -s --insecure "$EDGE_URL" >/dev/null 2>&1; then
      HEALTH_OK=1
      break 2
    fi
    sleep 1
  done
done

if [ "$HEALTH_OK" -ne 1 ]; then
  echo "LocalStack edge endpoint not reachable after retries. Exiting."
  exit 1
fi

echo "Using LocalStack endpoint: $EDGE_URL"

# If we're using HTTPS, AWS CLI will validate the certificate; LocalStack uses a self-signed cert
# where the CN/SANs may not match 'localhost'. To avoid failures, use --no-verify-ssl with aws CLI
AWS_CLI_INSECURE=""
if [[ "$EDGE_URL" == https://* ]]; then
  AWS_CLI_INSECURE="--no-verify-ssl"
fi

# Resource naming per perspective (use sanitized perspective)
TOPIC_NAME="${PERSPECTIVE_SAFE}-topic"
BUCKET="etl-${PERSPECTIVE_SAFE}-client-etl"
TOPIC_ARN=""

echo "Creating S3 bucket: $BUCKET"
# Use aws CLI create-bucket; LocalStack accepts it. S3 bucket names must be lowercase and no underscores.
aws $AWS_CLI_INSECURE --endpoint-url="$EDGE_URL" --region "$AWS_REGION" s3 mb "s3://$BUCKET" || true

echo "Creating SNS topic: $TOPIC_NAME"
# Capture the TopicArn from create-topic for use in subscribe
TOPIC_ARN=$(aws $AWS_CLI_INSECURE --endpoint-url="$EDGE_URL" --region "$AWS_REGION" sns create-topic --name "$TOPIC_NAME" --output text --query 'TopicArn' 2>/dev/null || true)
if [ -z "$TOPIC_ARN" ]; then
  echo "Failed to create or retrieve TopicArn for $TOPIC_NAME"
else
  echo "Created SNS topic: $TOPIC_ARN"
fi

# Subscribe the HTTP endpoint (LocalStack will deliver to host.docker.internal:PORT)
SUB_ENDPOINT="http://${LISTENER_HOST}:${LISTENER_PORT}/"
if [ -n "$TOPIC_ARN" ]; then
  aws $AWS_CLI_INSECURE --endpoint-url="$EDGE_URL" --region "$AWS_REGION" sns subscribe --topic-arn "$TOPIC_ARN" --protocol http --notification-endpoint "$SUB_ENDPOINT" >/dev/null || true
else
  echo "Skipping subscribe since TopicArn is missing"
fi

echo "LocalStack setup complete for perspective: $PERSPECTIVE (sanitized: $PERSPECTIVE_SAFE)"
echo "S3 bucket: $BUCKET"
echo "SNS topic ARN: ${TOPIC_ARN:-<missing>}"
echo "HTTP subscription endpoint: $SUB_ENDPOINT"

echo "You can publish a test message with:"
echo "aws $AWS_CLI_INSECURE --endpoint-url=$EDGE_URL --region $AWS_REGION sns publish --topic-arn ${TOPIC_ARN:-<topic_arn>} --message '{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"$BUCKET\"},\"object\":{\"key\":\"from_client/nm_albuquerque/organizations/Officer_Detail.csv\"}}}]}'"
