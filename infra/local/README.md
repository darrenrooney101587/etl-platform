# Local development with LocalStack

This folder contains helper artifacts to run a local AWS stack (SNS + S3) using LocalStack so you can develop and test packages in this monorepo without talking to real AWS.

Perspectives
- The monorepo contains multiple perspectives (projects): `file_processing`, `data_pipeline`, and `observability`.
- This setup supports configuring LocalStack resources scoped per perspective so tests and local integrations remain isolated.

This folder contains:
- `docker/` - LocalStack docker compose files
- `scripts/setup_localstack.sh` - helper to create S3 bucket, SNS topic and subscribe your local listener

Requirements
- Docker & docker-compose
- AWS CLI

Quickstart

1. Start LocalStack

```bash
cd infra/local
# start LocalStack using the compose file in infra/local/docker
docker-compose -f docker/docker-compose.yml up -d
```

2. Run the setup script (perspective-aware)

```bash
# From repo root (preferred)
infra/local/scripts/setup_localstack.sh host.docker.internal 8080 file_processing

# for data_pipeline perspective
infra/local/scripts/setup_localstack.sh host.docker.internal 8080 data_pipeline

# for observability perspective
infra/local/scripts/setup_localstack.sh host.docker.internal 8080 observability
```

The script will create an S3 bucket named `etl-<perspective>-client-etl` and an SNS topic named `<perspective>-topic`, and subscribe the topic to `http://<listener_host>:<listener_port>/`.

3. Publish a test message

```bash
EDGE=http://localhost:4566
# Example ARN for file_processing perspective created by the setup script
TOPIC_ARN=arn:aws:sns:us-east-1:000000000000:file_processing-topic
aws --endpoint-url="$EDGE" sns publish --topic-arn "$TOPIC_ARN" --message '{"Records":[{"s3":{"bucket":{"name":"etl-file_processing-client-etl"},"object":{"key":"from_client/nm_albuquerque/organizations/Officer_Detail.csv"}}}]}'
```

Notes
- Use `host.docker.internal` on macOS so LocalStack can reach your host-based listener. Adjust the host for Linux if needed.
- The LocalStack edge port is `4566`.
- These resources are ephemeral and intended for local development only.

## Per-perspective helper scripts

To make it easy to create LocalStack resources for a specific package/perspective, we provide small wrapper scripts under `infra/<perspective>/scripts/` that call the central `infra/local/scripts/setup_localstack.sh` with the correct perspective argument.

Available wrappers (examples):

- `infra/file_processing/scripts/setup_localstack.sh` — prepare LocalStack for the `file_processing` perspective
- `infra/data_pipeline/scripts/setup_localstack.sh` — prepare LocalStack for the `data_pipeline` perspective

Usage (examples):

```bash
# File processing (default resources)
infra/file_processing/scripts/setup_localstack.sh host.docker.internal 8080

# Data pipeline
infra/data_pipeline/scripts/setup_localstack.sh host.docker.internal 8080
```

These wrappers are thin and only provide a nicer developer UX; they call `infra/local/scripts/setup_localstack.sh` with the right perspective.
