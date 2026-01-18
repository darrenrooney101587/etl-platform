#!/usr/bin/env bash
set -euo pipefail

ACCOUNT_ID="${ACCOUNT_ID:-270022076279}"
BUCKET="${BUCKET:-etl-ba-research-client-etl}"
TOPIC_ARN="${TOPIC_ARN:-arn:aws-us-gov:sns:us-gov-west-1:${ACCOUNT_ID}:pipeline-processing-topic}"
AWS_PROFILE="${AWS_PROFILE:-etl-playground}"
AWS_REGION="${AWS_REGION:-us-gov-west-1}"

cat > /tmp/sns-topic-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3PublishFromSpecificBucket",
      "Effect": "Allow",
      "Principal": { "Service": "s3.amazonaws.com" },
      "Action": "sns:Publish",
      "Resource": "${TOPIC_ARN}",
      "Condition": {
        "ArnLike": { "aws:SourceArn": "arn:aws-us-gov:s3:::${BUCKET}" },
        "StringEquals": { "aws:SourceAccount": "${ACCOUNT_ID}" }
      }
    }
  ]
}
EOF

aws sns set-topic-attributes \
  --topic-arn "${TOPIC_ARN}" \
  --attribute-name Policy \
  --attribute-value file:///tmp/sns-topic-policy.json \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}"
