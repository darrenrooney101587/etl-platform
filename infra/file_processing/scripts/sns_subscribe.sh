#!/usr/bin/env bash
set -euo pipefail

SNS_TOPIC_ARN="${SNS_TOPIC_ARN:-arn:aws-us-gov:sns:us-gov-west-1:270022076279:file-processing-topic}"
ENDPOINT="${ENDPOINT:-http://localhost/}"
AWS_PROFILE="${AWS_PROFILE:-etl-playground}"
AWS_REGION="${AWS_REGION:-us-gov-west-1}"

aws sns subscribe \
  --topic-arn "${SNS_TOPIC_ARN}" \
  --protocol http \
  --notification-endpoint "${ENDPOINT}" \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}"
