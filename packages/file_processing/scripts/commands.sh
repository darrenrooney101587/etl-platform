#!/usr/bin/env bash
set -euo pipefail

# Build the image first
./packages/file_processing/scripts/build.sh

NETWORK=${NETWORK:-local_default}
JOB_NAME=${1:-sns_listener}

# Check if arguments were provided (so we can shift $1 safely)
if [ "$#" -ge 1 ]; then
    shift
fi

# Run the job in a disposable container (one-shot)
docker run --rm \
  --name file-processing-"$JOB_NAME" \
  --network "$NETWORK" \
  -v "$PWD":/app -w /app \
  --env-file packages/file_processing/.env \
  -e PYTHONPATH=/app/packages \
  etl-file-processing \
  python -m file_processing.cli.main run "$JOB_NAME" "$@"



TOPIC_ARN=arn:aws:sns:us-east-1:000000000000:file-processing-topic
docker run --rm --network "$NETWORK" -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test \
  amazon/aws-cli --endpoint-url http://localstack:4566 --region us-east-1 \
  sns subscribe --topic-arn "$TOPIC_ARN" --protocol http --notification-endpoint "http://file-processing-listener:8080/"


EVENT=$(python -c 'import json,sys; print(json.dumps(json.load(open("packages/file_processing/event.json"))))')
docker run --rm --network "$NETWORK" -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test \
  amazon/aws-cli --endpoint-url http://localstack:4566 --region us-east-1 \
  sns publish --topic-arn "$TOPIC_ARN" --message "$EVENT"
