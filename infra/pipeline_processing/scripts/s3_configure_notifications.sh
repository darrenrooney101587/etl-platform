#!/usr/bin/env bash
set -euo pipefail

# Configure S3 bucket to publish ObjectCreated events to SNS topic
BUCKET="${BUCKET:-etl-ba-research-client-etl}"
TOPIC_ARN="${TOPIC_ARN:-arn:aws-us-gov:sns:us-gov-west-1:270022076279:pipeline-processing-topic}"
AWS_PROFILE="${AWS_PROFILE:-etl-playground}"
AWS_REGION="${AWS_REGION:-us-gov-west-1}"

cat > /tmp/s3-notification.json <<EOF
{
  "TopicConfigurations": [
    {
      "TopicArn": "${TOPIC_ARN}",
      "Events": ["s3:ObjectCreated:*"]
    }
  ]
}
EOF

aws s3api put-bucket-notification-configuration \
  --bucket "${BUCKET}" \
  --notification-configuration file:///tmp/s3-notification.json \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}"

# To verify, run:
# aws s3api get-bucket-notification-configuration --bucket "${BUCKET}" --profile "${AWS_PROFILE}" --region "${AWS_REGION}"
