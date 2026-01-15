#!/usr/bin/env bash
# packages/file_processing/scripts/commands.sh
# Concise runbook: build, run listener (containerized), subscribe, publish, verify.

# Build image
./packages/file_processing/scripts/build.sh

# Start listener container on LocalStack network (replace NETWORK if different)
NETWORK=local_default

docker run -d \
  --name file-processing-listener \
  --network "$NETWORK" \
  -v "$PWD":/app -w /app \
  --env-file packages/file_processing/.env \
  -e PYTHONPATH=/app/packages \
  --entrypoint python \
  etl-file-processing \
  -m file_processing.cli.sns_main

# Subscribe listener endpoint to topic (idempotent)
TOPIC_ARN=arn:aws:sns:us-east-1:000000000000:file-processing-topic

docker run --rm --network "$NETWORK" -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test \
  amazon/aws-cli --endpoint-url http://localstack:4566 --region us-east-1 \
  sns subscribe --topic-arn "$TOPIC_ARN" --protocol http --notification-endpoint "http://file-processing-listener:8080/"

# Publish test event
EVENT=$(python -c 'import json,sys; print(json.dumps(json.load(open("packages/file_processing/event.json"))))')

docker run --rm --network "$NETWORK" -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test \
  amazon/aws-cli --endpoint-url http://localstack:4566 --region us-east-1 \
  sns publish --topic-arn "$TOPIC_ARN" --message "$EVENT"

# Tail listener logs to confirm receipt and job execution
docker logs -f file-processing-listener

# Host-runner alternative (start listener locally on host)
# ./packages/file_processing/scripts/run_local_listener.sh 8080 > /tmp/sns_listener.log 2>&1 & echo $! > /tmp/sns_listener.pid
# Then publish using host networking:
# docker run --rm --network host -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test amazon/aws-cli \
#   --endpoint-url http://localhost:4566 --region us-east-1 sns publish --topic-arn "$TOPIC_ARN" --message "$EVENT"
