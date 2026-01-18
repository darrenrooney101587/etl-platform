#!/usr/bin/env bash
set -euo pipefail

TOPIC_ARN="${TOPIC_ARN:-arn:aws-us-gov:sns:us-gov-west-1:270022076279:pipeline-processing-topic}"
AWS_PROFILE="${AWS_PROFILE:-etl-playground}"
AWS_REGION="${AWS_REGION:-us-gov-west-1}"

aws sns list-subscriptions-by-topic \
  --topic-arn "${TOPIC_ARN}" \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}"
