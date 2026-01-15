# file_processing

This package contains the file processing components for the ETL platform: the SNS listener, the S3 data quality job, processors, repositories, and tests.

## SNS listener runtime behavior

The SNS HTTP listener (`packages/file_processing/cli/sns_main.py`) implements a small in-process HTTP server that accepts AWS SNS HTTP POST requests and forwards the inner S3 event message to the data quality job.

Key behaviors:

- Concurrency control: the server uses a bounded `ThreadPoolExecutor` to limit the number of concurrent job executions in a single pod. Configure with the environment variable `SNS_WORKER_MAX` (default: `10`).

- Circuit breaker: to avoid repeated failing work consuming resources and spamming logs, the server includes a per-pod `CircuitBreaker`.
  - Env vars:
    - `CIRCUIT_BREAKER_MAX_FAILURES` (default `5`) — consecutive failing jobs before the breaker activates.
    - `CIRCUIT_BREAKER_COOLDOWN_SECONDS` (default `60`) — how long to wait before the breaker auto-resets.
  - While active the handler will skip submitting new jobs and respond with `{"status": "skipped"}`. You can change this behavior to return a 5xx if you prefer SNS to retry automatically.
  - The circuit breaker is per-pod (in-memory). Restarting the pod will reset the breaker.

- Admin endpoints (development):
  - `GET /breaker` — inspect breaker state: `active`, `consecutive_failures`, `last_failure_time`, and `cooldown_remaining`.
  - `GET /breaker/reset` — reset the breaker immediately (useful in development).

## Why both a thread pool and a circuit breaker?

They solve different operational problems:
- Thread pool (`ThreadPoolExecutor`) bounds concurrency, protecting CPU, memory and external resources (DB connections) during bursts.
- Circuit breaker stops repeated failing work (failure throttling) while you fix underlying issues.

Both together are recommended for a robust in-process listener.

## Testing

This package uses `unittest.TestCase` for unit tests.

Run the package tests with:

```bash
python -m unittest discover packages/file_processing/tests -v
```

We include tests that cover the `CircuitBreaker` behavior and the S3 `NoSuchKey` handling in the processor.

## Local Docker development (recommended)

`file_processing` imports ORM models from `etl_database_schema`. To avoid pulling the schema package from GitLab/VPN during each Docker build, we use a sibling checkout staged into the Docker build context.

1) One-time: clone the schema repo next to this repo:
```bash
git clone git@gitlab.dev-benchmarkanalytics.com:etl/etl-database-schema.git ../etl-database-schema
```

2) Ensure you have a local env file:
```bash
cp packages/file_processing/.env.example packages/file_processing/.env
```

3) Build the local image (stages schema into `.local/etl-database-schema` and builds from repo root):
```bash
./packages/file_processing/scripts/build.sh
```

4) Run the SNS listener (containerized, recommended)

Run the listener inside a container and attach it to the same Docker network as LocalStack so LocalStack can POST directly to the container by name:

```bash
# Start the listener container (use repo root). The ENTRYPOINT in the image is the package CLI, so override to run the SNS module.
NETWORK=local_default  # the LocalStack network name (inspect if different)

docker run -d \
  --name file-processing-listener \
  --network "$NETWORK" \
  -v "$PWD":/app -w /app \
  --env-file packages/file_processing/.env \
  -e PYTHONPATH=/app/packages \
  --entrypoint python \
  etl-file-processing \
  -m file_processing.cli.sns_main

# Verify container is running and attached to the network
docker ps --filter name=file-processing-listener
```

5) Ensure LocalStack topic exists & subscribe the container endpoint (if not auto-created)

Use the aws CLI on the LocalStack network so `localstack` resolves and the subscription endpoint can be the container name.

```bash
NETWORK=local_default
TOPIC_ARN=arn:aws:sns:us-east-1:000000000000:file-processing-topic

# subscribe container endpoint (idempotent)
docker run --rm --network "$NETWORK" -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test \
  amazon/aws-cli --endpoint-url http://localstack:4566 --region us-east-1 \
  sns subscribe --topic-arn "$TOPIC_ARN" --protocol http --notification-endpoint "http://file-processing-listener:8080/"

# list subscriptions
docker run --rm --network "$NETWORK" -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test \
  amazon/aws-cli --endpoint-url http://localstack:4566 --region us-east-1 \
  sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" --output json
```

6) Publish a test event and verify processing

```bash
# Build compact JSON and publish (on the same network)
EVENT=$(python -c 'import json,sys; print(json.dumps(json.load(open("packages/file_processing/event.json"))))')

docker run --rm --network "$NETWORK" -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test \
  amazon/aws-cli --endpoint-url http://localstack:4566 --region us-east-1 \
  sns publish --topic-arn "$TOPIC_ARN" --message "$EVENT"

# Tail listener logs to see receipt and job execution
docker logs -f file-processing-listener

# Check dry-run output (listener container mounts the repo to /app so file appears on host)
ls -l ./dry_run_results.jsonl || echo "dry_run_results.jsonl not found in repo root"
```

Host-runner alternative (quick dev loop)

If you prefer to run the listener on the host (no container), start it and publish to the pre-created topic using `host.docker.internal` as the subscription endpoint. This is useful for fast iteration and local debugging:

```bash
# start listener on host
./packages/file_processing/scripts/run_local_listener.sh 8080 > /tmp/sns_listener.log 2>&1 & echo $! > /tmp/sns_listener.pid

# publish via aws CLI container using host networking
EVENT=$(python -c 'import json,sys; print(json.dumps(json.load(open("packages/file_processing/event.json"))))')

docker run --rm --network host -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test \
  amazon/aws-cli --endpoint-url http://localhost:4566 --region us-east-1 \
  sns publish --topic-arn "$TOPIC_ARN" --message "$EVENT"

# tail logs
tail -f /tmp/sns_listener.log
```

When `etl-database-schema` changes, run `git pull` in `../etl-database-schema` and rebuild:
```bash
cd ../etl-database-schema && git pull
cd -
./packages/file_processing/scripts/build.sh
```

## Notes
- The SNS listener invokes the job in-process using a background thread; logs and dry-run outputs appear where the listener runs (host terminal or container logs).
- If you prefer jobs to run in separate containers or worker processes, we can change the listener to spawn a container or push messages to an SQS queue and run workers separately.
