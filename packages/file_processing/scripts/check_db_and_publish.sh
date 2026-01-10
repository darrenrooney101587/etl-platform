#!/usr/bin/env bash
set -euo pipefail

AWS_PROFILE=${AWS_PROFILE:-etl-playground}
AWS_REGION=${AWS_REGION:-us-gov-west-1}
NAMESPACE=${NAMESPACE:-file-processing}
LABEL=${LABEL:-app=file-processing-sns}
TIMEOUT=${TIMEOUT:-30}

TF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)/infra/file_processing"

# Topic ARN from Terraform output (fallback to env override)
TOPIC_ARN=${SNS_TOPIC_ARN:-$(terraform -chdir="$TF_DIR" output -raw sns_topic_arn 2>/dev/null || true)}
if [ -z "$TOPIC_ARN" ]; then
  echo "ERROR: SNS topic ARN not found. Set SNS_TOPIC_ARN env or ensure terraform output is available."
  exit 1
fi

# Find a pod
POD=$(kubectl -n "$NAMESPACE" get pods -l "$LABEL" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -z "$POD" ]; then
  echo "ERROR: No pod found in namespace $NAMESPACE with label $LABEL"
  kubectl -n "$NAMESPACE" get pods || true
  exit 1
fi

echo "Using pod: $POD"

echo "--- Pod DB env vars ---"
kubectl -n "$NAMESPACE" exec "$POD" -- /bin/sh -c 'echo DB_HOST=$DB_HOST; echo DB_PORT=$DB_PORT; echo DB_NAME=$DB_NAME; echo DB_USER=$DB_USER; echo DB_PASSWORD=${DB_PASSWORD:+<set>}'

# Try DB connection from inside pod using Python + psycopg2 (container already has runtime deps)
echo "--- attempting psycopg2 connect inside pod (8s timeout) ---"
set +e
kubectl -n "$NAMESPACE" exec "$POD" -- python - <<'PY'
import os,sys
try:
    import psycopg2
except Exception as e:
    print('psycopg2 import failed:', e)
    sys.exit(2)
host=os.getenv('DB_HOST')
port=os.getenv('DB_PORT','5432')
name=os.getenv('DB_NAME')
user=os.getenv('DB_USER')
pw=os.getenv('DB_PASSWORD')
print('connecting to', host, port, name, user)
try:
    conn = psycopg2.connect(host=host, port=int(port), dbname=name, user=user, password=pw, connect_timeout=8)
    conn.close()
    print('DB connection: SUCCESS')
    sys.exit(0)
except Exception as e:
    print('DB connection: FAILED', e)
    sys.exit(1)
PY
RC=$?
set -e

if [ $RC -ne 0 ]; then
  echo "DB connectivity test failed from inside pod (exit $RC). Check DB credentials and network ACLs/security groups."
else
  echo "DB connectivity test succeeded from inside pod."
fi

# Publish a test SNS message
TMPMSG=$(mktemp /tmp/snsmsg.XXXX.json)
cat > "$TMPMSG" <<'JSON'
{"Records":[{"eventVersion":"2.1","eventSource":"aws:s3","awsRegion":"us-gov-west-1","eventTime":"2026-01-09T16:48:19.000Z","eventName":"ObjectCreated:Put","s3":{"s3SchemaVersion":"1.0","configurationId":"ConfigId","bucket":{"name":"etl-ba-research-client-etl","arn":"arn:aws-us-gov:s3:::etl-ba-research-client-etl"},"object":{"key":"from_client/nm_albuquerque/Officer_Detail.csv","size":12345,"eTag":"abcd1234","sequencer":"0123456789"}}}]}
JSON

echo "Publishing SNS message to $TOPIC_ARN (profile=$AWS_PROFILE region=$AWS_REGION)"
aws sns publish --topic-arn "$TOPIC_ARN" --message file://"$TMPMSG" --profile "$AWS_PROFILE" --region "$AWS_REGION"
rm -f "$TMPMSG"

# Tail logs for TIMEOUT seconds to capture processing
echo "Tailing logs for $TIMEOUT seconds..."
timeout "$TIMEOUT" kubectl -n "$NAMESPACE" logs -l "$LABEL" -f --timestamps || true

echo "Done."
