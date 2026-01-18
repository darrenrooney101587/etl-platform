# Local development with LocalStack

This folder contains helper artifacts to run a local AWS stack (SNS + S3) using LocalStack to enable local development and testing of packages in this monorepo without contacting real AWS.

Perspectives
- The monorepo contains multiple perspectives (projects): `pipeline_processing` and `observability`.
- This setup supports configuring LocalStack resources scoped per perspective so tests and local integrations remain isolated.

This folder contains:
- `docker/` - LocalStack docker compose files
- `scripts/setup_localstack.sh` - helper to create S3 bucket, SNS topic and subscribe the local listener

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
infra/local/scripts/setup_localstack.sh host.docker.internal 8080 pipeline_processing

# for observability perspective
infra/local/scripts/setup_localstack.sh host.docker.internal 8080 observability
```

The script will create an S3 bucket named `etl-<perspective>-client-etl` and an SNS topic named `<perspective>-topic`, and subscribe the topic to `http://<listener_host>:<listener_port>/`.

3. Publish a test message

```bash
EDGE=http://localhost:4566
# Example ARN for pipeline_processing perspective created by the setup script
TOPIC_ARN=arn:aws:sns:us-east-1:000000000000:pipeline_processing-topic
aws --endpoint-url="$EDGE" sns publish --topic-arn "$TOPIC_ARN" --message '{"Records":[{"s3":{"bucket":{"name":"etl-pipeline_processing-client-etl"},"object":{"key":"from_client/nm_albuquerque/organizations/Officer_Detail.csv"}}}]}'
```

Notes
- Use `host.docker.internal` on macOS so LocalStack can reach a host-based listener. Adjust the host for Linux if needed.
- The LocalStack edge port is `4566`.
- These resources are ephemeral and intended for local development only.

## Per-perspective helper scripts

To make it easy to create LocalStack resources for a specific package/perspective, small wrapper scripts are provided under `infra/<perspective>/scripts/` that call the central `infra/local/scripts/setup_localstack.sh` with the perspective argument.

Available wrappers follow the pattern `infra/<perspective>/scripts/setup_localstack.sh` and call the central setup script with the matching perspective.

These wrappers are thin and only provide a simpler developer UX; they call `infra/local/scripts/setup_localstack.sh` with the correct perspective.
