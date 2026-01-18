#!/usr/bin/env bash
set -euo pipefail

# Lightweight test helper to publish a sample SNS S3-event JSON to the pipeline-processing topic.
# Usage: ./sns_test_topic.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prefer git repo root if available, otherwise fall back to relative path math
if git -C "$SCRIPT_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then
  REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
else
  # Script lives at: <repo-root>/infra/pipeline_processing/scripts
  # go up three levels to reach repo root
  REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
fi

# Terraform directory for the pipeline_processing infra (repo-root/infra/pipeline_processing/terraform)
TF_DIR="$REPO_ROOT/infra/pipeline_processing/terraform"

echo "Repo root: $REPO_ROOT"
echo "Terraform dir: $TF_DIR"

SNS_TOPIC_ARN="${SNS_TOPIC_ARN:-$(terraform -chdir="$TF_DIR" output -raw sns_topic_arn 2>/dev/null || true)}"
if [ -z "$SNS_TOPIC_ARN" ]; then
  echo "ERROR: terraform output sns_topic_arn is empty or terraform failed."
  echo "Run: terraform -chdir=$TF_DIR output -json to debug. (Checked TF_DIR above)"
  exit 1
fi

# Basic validation: ARN should contain at least 6 ':' segments (arn:partition:service:region:account:resource)
COLON_COUNT=$(awk -F":" '{print NF-1}' <<<"$SNS_TOPIC_ARN")
if [ "$COLON_COUNT" -lt 5 ]; then
  echo "ERROR: Topic ARN appears invalid: '$SNS_TOPIC_ARN'"
  exit 1
fi

TMP_MSG_FILE="$(mktemp 2>/dev/null || mktemp /tmp/sns-msg.XXXXXX)"
# Ensure we remove the temp file on exit (safe no-op if file already removed)
trap 'rm -f "$TMP_MSG_FILE" >/dev/null 2>&1 || true' EXIT

cat > "$TMP_MSG_FILE" <<'JSON'
{"Records":[{"eventVersion":"2.1","eventSource":"aws:s3","awsRegion":"us-gov-west-1","eventTime":"2026-01-09T16:48:19.000Z","eventName":"ObjectCreated:Put","s3":{"s3SchemaVersion":"1.0","configurationId":"ConfigId","bucket":{"name":"etl-ba-research-client-etl","arn":"arn:aws-us-gov:s3:::etl-ba-research-client-etl"},"object":{"key":"from_client/nm_albuquerque/organizations/Officer_Detail.csv","size":12345,"eTag":"abcd1234","sequencer":"0123456789"}}}]}
JSON

echo "Publishing SNS message to: $SNS_TOPIC_ARN"
aws sns publish --topic-arn "$SNS_TOPIC_ARN" --message file://"$TMP_MSG_FILE" --profile "etl-playground" --region "us-gov-west-1"

echo "Publish complete"
