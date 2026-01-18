# observability infra

This stack manages infrastructure needed to run the `observability` module (job-driven notification backend).

It follows the same workflow shape as `infra/file_processing`:
- local Docker run for fast iteration
- LocalStack helpers for AWS-mocking workflows
- manual push + deploy into the `etl-playground` AWS account

## Prereqs
- `infra/plumbing` applied (shared VPC/subnets outputs available).
- AWS credentials with rights to EKS/ECR/IAM in the target account.
- Docker + kubectl installed locally.

## A) Run the container locally (fast iteration)

The module Dockerfile lives under the package:
- `packages/observability/observability.Dockerfile`

Build it:
```bash
docker build -f packages/observability/observability.Dockerfile -t observability:local .
```

Run it (example: list available commands):
```bash
docker run --rm -e PYTHONUNBUFFERED=1 observability:local \
  python -m observability.cli.main list
```

Run a job module (example):
```bash
docker run --rm \
  -e PYTHONUNBUFFERED=1 \
  -e DATABASE_URL="${DATABASE_URL}" \
  -e SLACK_BOT_TOKEN="${SLACK_BOT_TOKEN}" \
  observability:local \
  python -m observability.jobs.daily_digest
```

Notes:
- This module is designed to run as ad-hoc/scheduled jobs. It is not a web service.
- See `packages/observability/README.md` for job inventory and environment variables.

## B) LocalStack (mimic AWS actions)

Use the module wrapper script (delegates to `infra/local/scripts/setup_localstack.sh`):

```bash
cd infra/observability
./scripts/setup_localstack.sh host.docker.internal 8080
```

This will:
- start LocalStack (if needed)
- create a perspective-specific S3 bucket and SNS topic
- subscribe an HTTP endpoint to the SNS topic

When `observability` does not run an HTTP listener, the created bucket/topic remain available for manual testing (publish events, create objects, etc).

## C) Push to `etl-playground` (AWS testing)

### Terraform lifecycle

```bash
cd infra/observability
./scripts/manage.sh init
./scripts/manage.sh plan
./scripts/manage.sh apply
```

Destroy (danger):
```bash
cd infra/observability
./scripts/manage.sh destroy
```

### Build + push image and update the deployment

```bash
cd infra/observability
./scripts/manage.sh update-image
```

Notes:
- `./scripts/ecr_put.sh` builds and pushes using an ECR image URI read from `infra/observability/terraform/container_image.txt`.
- If `container_image.txt` is missing, run `./scripts/manage.sh outputs` (or apply) and ensure the terraform stack writes `container_image.txt`.
