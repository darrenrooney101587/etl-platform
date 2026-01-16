#!/usr/bin/env bash
./packages/file_processing/scripts/build.sh
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


TOPIC_ARN=arn:aws:sns:us-east-1:000000000000:file-processing-topic
docker run --rm --network "$NETWORK" -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test \
  amazon/aws-cli --endpoint-url http://localstack:4566 --region us-east-1 \
  sns subscribe --topic-arn "$TOPIC_ARN" --protocol http --notification-endpoint "http://file-processing-listener:8080/"


EVENT=$(python -c 'import json,sys; print(json.dumps(json.load(open("packages/file_processing/event.json"))))')
docker run --rm --network "$NETWORK" -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test \
  amazon/aws-cli --endpoint-url http://localstack:4566 --region us-east-1 \
  sns publish --topic-arn "$TOPIC_ARN" --message "$EVENT"
