# data_pipeline

Combined transforms + ingestion runtime lane.
Compute + side‑effecting writes.

## Responsibilities
- S3‑based transforms (bronze → silver)
- Enrichment & normalization
- Backfills / reprocessing
- Application API ingestion
- Idempotency, batching, DLQ, audit trails

## Migration Notes
This package contains the migrated code from `etl-data-extraction`.
The legacy `service` app has been refactored into a pure Python module.
Django project artifacts (manage.py, etc.) have been removed.

## Execution (recommended)
This package is a "jobs" module: it exposes small, testable CLI entrypoints
that orchestrate job work (construct `ServiceHandler`, run operations, print
results). The recommended production pattern is to bake a container image that
installs the package and its dependencies and sets a console script as the
container ENTRYPOINT — then K8s (EKS) Jobs or other orchestration can provide
only the CLI arguments.

Why this is recommended
- No Django runtime required in the image (Django belongs to `etl-database-schema` only).
- Reproducible images: dependencies are installed at build time.
- EKS Jobs: keep ENTRYPOINT stable; pass only args in Job manifests.
- Easier testing and DI: `cli` modules are lightweight and unit-testable.

Console scripts
- `data-pipeline` → general module entrypoint (configured as the image ENTRYPOINT in our Dockerfile).
- `data-pipeline-get-s3-files` → specific job CLI that runs the S3 file processing flow.

Preferred production run (ENTRYPOINT set to console script)
```bash
# Image must be built so the console script is installed and available as the ENTRYPOINT.
# The Job only passes arguments to the container.
docker run --rm etl-data-pipeline \
  --agency-id 10 \
  --source-bucket benchmarkanalytics-production-env-userdocument-test \
  --destination-bucket etl-ba-research-client-etl
```

Fallback production run (explicit invocation)
```bash
# If the image does not set ENTRYPOINT, invoke the console script explicitly.
docker run --rm etl-data-pipeline \
  data-pipeline-get-s3-files --agency-id 10 \
  --source-bucket benchmarkanalytics-production-env-userdocument-test \
  --destination-bucket etl-ba-research-client-etl
```

Developer workflow (mount source, auto-install deps)
```bash
# Mount local source into the container and use the dev entrypoint which
# will install dependencies if necessary. This is for iterative development.
docker run --rm -it \
  -v "$(pwd)/packages/data_pipeline:/app/packages/data_pipeline" \
  -v "$(pwd)/packages/etl_core:/app/packages/etl_core" \
  --workdir /app/packages/data_pipeline \
  --entrypoint /app/packages/data_pipeline/config_scripts/docker-entrypoint.sh \
  etl-data-pipeline \
  poetry run data-pipeline-get-s3-files --agency-id 10
```
Set environment variable `SKIP_INSTALL=1` when you are sure dependencies are present and you want to skip the install step.

Kubernetes Job example (EKS)
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: get-s3-files-job
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: get-s3-files
          image: ghcr.example.com/your-org/etl-data-pipeline:latest
          # Preferred: set the image ENTRYPOINT to the console script and pass args only
          command: ["data-pipeline"]
          args:
            - "--agency-id"
            - "10"
            - "--source-bucket"
            - "benchmarkanalytics-production-env-userdocument-test"
            - "--destination-bucket"
            - "etl-ba-research-client-etl"
      backoffLimit: 1
```

Avoid `docker exec` for jobs
- Using `docker exec` to run commands inside a running container is useful for debugging,
  but it is not a robust pattern for jobs. Jobs should be modeled as short-lived
  containers started with the correct ENTRYPOINT/command. This yields reproducibility
  and aligns with K8s semantics.

Running the module directly
- If you need to run without an installed console script, you can run the module
  with Python: `python -m data_pipeline.cli.get_s3_files --help`.

## How to run locally
### Local development
```bash
poetry install --extras db
poetry run data-pipeline-get-s3-files --help
```

### Docker (build & run example)
```bash
# Build from repository root (module Dockerfile builds package into image)
docker build -f docker/data-pipeline.Dockerfile -t etl-data-pipeline .

# Run preferred ENTRYPOINT form (pass only args)
docker run --rm etl-data-pipeline \
  --agency-id 10 \
  --source-bucket benchmarkanalytics-production-env-userdocument-test \
  --destination-bucket etl-ba-research-client-etl
```
