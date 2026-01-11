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

## Notes

- The circuit breaker and the admin endpoints are intended for development and operational visibility. If you require cluster-wide throttling you should implement a shared state (DB/Redis) or use SNS→SQS with a single worker group.
- Ensure `IRSA` (IAM role for service accounts) is configured in the cluster so pods can access S3 safely (no long-lived AWS keys in pod envs). See infra docs for `file_processing` for details.
