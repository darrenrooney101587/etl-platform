fe# reporting_seeder infra

This stack provisions infrastructure for `reporting_seeder`, pulling shared VPC/subnet outputs from `infra/plumbing`.

It follows the same workflow shape as `infra/file_processing`:
- local Docker run for fast iteration
- LocalStack helpers for AWS-mocking workflows
- manual push + deploy into the `etl-playground` AWS account

## Prereqs
- `infra/plumbing` applied (VPC/subnets/NAT outputs available).
- AWS credentials with rights to create EKS/ECR/IAM.
- Docker + kubectl installed locally.

## A) Run the container locally (fast iteration)

The module Dockerfile lives under the package:
- `packages/reporting_seeder/reporting-seeder.Dockerfile`

Build it:
```bash
docker build -f packages/reporting_seeder/reporting-seeder.Dockerfile -t reporting-seeder:local .
```

Run the CLI (example):
```bash
docker run --rm -e PYTHONUNBUFFERED=1 reporting-seeder:local \
  python -m reporting_seeder.cli.main
```

Local DB connectivity

To provide DB connectivity to the container, set a `DATABASE_URL` (or the envs expected by the package settings):
```bash
docker run --rm \
  -e PYTHONUNBUFFERED=1 \
  -e DATABASE_URL="${DATABASE_URL}" \
  reporting-seeder:local \
  python -m reporting_seeder.cli.main
```

Package env references:
- `packages/reporting_seeder/.env.example`

## B) LocalStack (mimic AWS actions)

Use the module wrapper script (delegates to `infra/local/scripts/setup_localstack.sh`):

```bash
cd infra/reporting_seeder
./scripts/setup_localstack.sh host.docker.internal 8080
```

Behavior:
- Starts LocalStack (if needed)
- Creates a perspective-specific S3 bucket and SNS topic
- Subscribes an HTTP endpoint to the SNS topic

The LocalStack wrapper is optional; when SNS/S3 local emulation is not required the created resources can be ignored. The wrapper exists for repo-wide consistency.

## C) Push to `etl-playground` (AWS testing)

### Terraform lifecycle

```bash
cd infra/reporting_seeder
./scripts/manage.sh init
./scripts/manage.sh plan
./scripts/manage.sh apply
```

Destroy (danger):
```bash
cd infra/reporting_seeder
./scripts/manage.sh destroy
```

### Build + push image and update the deployment

```bash
cd infra/reporting_seeder
./scripts/manage.sh update-image
```

Notes:
- `./scripts/ecr_put.sh` builds and pushes using an ECR image URI read from `infra/reporting_seeder/terraform/container_image.txt`.
- If `container_image.txt` is missing, run `./scripts/manage.sh outputs` (or apply) and ensure the terraform stack writes `container_image.txt`.
