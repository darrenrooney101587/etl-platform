# pipeline_processing infra

This folder contains infrastructure helpers for `pipeline_processing` local workflows.

## A) Run the container locally (fast iteration)

Dockerfile (module-scoped): `packages/pipeline_processing/pipeline-processing.Dockerfile`.

Build:
```bash
docker build -f packages/pipeline_processing/pipeline-processing.Dockerfile -t pipeline-processing:local .
```

Run (example: list package CLI commands):
```bash
docker run --rm -e PYTHONUNBUFFERED=1 pipeline-processing:local \
  python -m pipeline_processing.cli.main list
```

## B) LocalStack (mimic AWS actions)

Use the module wrapper script:
```bash
cd infra/data_pipeline
./scripts/setup_localstack.sh host.docker.internal 8080
```

This delegates to `infra/local/scripts/setup_localstack.sh`.

## C) Push to `etl-playground` (AWS testing)

This module does not currently include a full terraform stack under `infra/data_pipeline/terraform`.

If a deployable infra stack is added later, it must follow the repo convention:
- `infra/data_pipeline/terraform/*`
- `infra/data_pipeline/scripts/manage.sh`
- `infra/data_pipeline/scripts/ecr_put.sh`
- `infra/data_pipeline/scripts/setup_localstack.sh`

Until then, use per-module Docker builds and the shared infra stacks.
