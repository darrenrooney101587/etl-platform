# SNS Listener Job

The SNS HTTP listener (`packages/file_processing/jobs/sns_listener.py`) implements a small in-process HTTP server that accepts AWS SNS HTTP POST requests and forwards the inner S3 event message to the data quality job.

## Runtime behavior

- **Concurrency control:** the server uses a bounded `ThreadPoolExecutor` to limit the number of concurrent job executions in a single pod. Configure with the environment variable `SNS_WORKER_MAX` (default: `10`).

- **Circuit breaker:** to avoid repeated failing work consuming resources and spamming logs, the server includes a per-pod `CircuitBreaker`.
  - Env vars:
    - `CIRCUIT_BREAKER_MAX_FAILURES` (default `5`) — consecutive failing jobs before the breaker activates.
    - `CIRCUIT_BREAKER_COOLDOWN_SECONDS` (default `60`) — how long to wait before the breaker auto-resets.
  - While active the handler will skip submitting new jobs and respond with `{"status": "skipped"}`. An alternate behavior is to return a 5xx response so SNS will retry automatically.
  - The circuit breaker is per-pod (in-memory). Restarting the pod will reset the breaker.

- **Admin endpoints** (development):
  - `GET /breaker` — inspect breaker state: `active`, `consecutive_failures`, `last_failure_time`, and `cooldown_remaining`.
  - `GET /breaker/reset` — reset the breaker immediately (useful in development).

### Why both a thread pool and a circuit breaker?

They solve different operational problems:
- Thread pool (`ThreadPoolExecutor`) bounds concurrency, protecting CPU, memory and external resources (DB connections) during bursts.
- Circuit breaker stops repeated failing work (failure throttling) while you fix underlying issues.

Both together are recommended for a robust in-process listener.

## Running locally

### 1. Containerized (Recommended)

Run the listener inside a container and attach it to the same Docker network as LocalStack so LocalStack can POST directly to the container by name.

The image must be built first (`./packages/file_processing/scripts/build.sh`).

```bash
# Start the listener container using the job runner
NETWORK=local_default  # the LocalStack network name (inspect if different)

# Run the sns_listener job
./packages/file_processing/scripts/commands.sh sns_listener

# Verify container is running and attached to the network
docker ps --filter name=file-processing-sns_listener
```

### 2. Subscribe LocalStack topic

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

### 3. Publish test event

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

### Host-runner alternative

If running the listener on the host (no container), start it and publish to the pre-created topic using `host.docker.internal` as the subscription endpoint. This option is useful for fast iteration and local debugging.

```bash
# Start directly via poetry
export DJANGO_SETTINGS_MODULE=file_processing.settings
poetry run python -m file_processing.cli.main run sns_listener
```

## Implementation Notes
- The SNS listener invokes the job in-process using a background thread; logs and dry-run outputs appear where the listener runs (host terminal or container logs).
- If separate containers or worker processes are required for job execution, the listener may be changed to spawn containers or push messages to an SQS queue and run workers separately.
