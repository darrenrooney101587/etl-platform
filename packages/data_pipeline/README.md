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

Set environment variable `SKIP_INSTALL=1` when you are sure dependencies are present and you want to skip the install
step.

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
          command: [ "data-pipeline" ]
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

## Adding a job

Follow these guidelines when adding a new job under `packages/data_pipeline/jobs`:

1. Create a module file named `packages/data_pipeline/jobs/<job_name>.py`.
2. Expose the job using the single supported convention:
    - The module MUST provide a top-level `JOB` variable as a lightweight tuple: `(entrypoint, description)`.
        - `entrypoint` is a callable `entrypoint(argv: List[str]) -> int`.
        - `description` is a short string used for listing/help.

   Example: `JOB = (entrypoint, "Normalize agency records")`.

   Rationale: a single convention keeps discovery simple, avoids ambiguous behavior,
   and makes automated tooling (CI, manifest generators) reliable. The lightweight
   tuple avoids importing registry types inside job modules and prevents circular
   import issues.
3. Keep the job focused: the job module should only wire up CLI parsing and call into business logic modules under
   `packages/data_pipeline` (or `etl_core` for shared utilities).
4. Use constructor injection and small functions/classes for external resources (S3 clients, DB clients). Default to
   production implementations but allow test injection.
5. Add unit tests with `unittest.TestCase` under `packages/data_pipeline/tests/unit` and mock external resources.

Minimal job template (copy into `packages/data_pipeline/jobs/my_job.py`):

```python
"""Example job: normalize agency records."""
import argparse
from typing import List


def _run(agency_id: int, dry_run: bool) -> int:
    """Business logic entry — keep this small and testable."""
    # ... call into your business modules in packages/data_pipeline/... or etl_core
    print(f"Running normalize for agency={agency_id} dry_run={dry_run}")
    return 0


def entrypoint(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="my-job")
    parser.add_argument("--agency-id", required=True, type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return _run(args.agency_id, args.dry_run)


# REQUIRED: expose a simple JOB tuple (entrypoint, description)
JOB = (entrypoint, "Normalize agency records")
```

Notes on naming and discovery

- The registry discovers any module under `data_pipeline.jobs` (except modules starting with `_` and `registry`).
- The import-time behavior should be safe: avoid heavy side-effects at import time — do initialization inside the
  entrypoint or _run function.

## Running jobs at scale (best practices)

1. Single image, many jobs
    - Build one container image that installs `packages/data_pipeline` and `etl_core`.
    - Set the container ENTRYPOINT to the console script `data-pipeline` (this is how the current Dockerfile is
      written).
    - Use `data-pipeline run <job_name> -- <job args...>` as the command for the Kubernetes Job. This keeps images
      stable and makes manifests small.

2. K8s Job patterns
    - Short-lived jobs: use a single Job per invocation. Pass only args in the manifest. Example:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: normalize-agency-123
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: normalize
          image: ghcr.example.com/your-org/etl-data-pipeline:latest
          command: [ "data-pipeline", "run", "my_job", "--", "--agency-id", "123" ]
      backoffLimit: 1
```

- Parallelism / batching: if you need to process many agencies concurrently, create a controller/job-generator that
  submits many Job objects, or use a single Job with a scatter step that enqueues work to a queue system (SQS, Pub/Sub)
  and have workers scale.

3. Idempotency and retries
    - Jobs must be idempotent. Use durable markers (DB rows, S3 keys, object metadata) to record progress.
    - Keep side-effects behind a small API surface (single class) so tests can mock it easily.

4. Secrets and credentials
    - Use K8s ServiceAccount and IRSA (for AWS) for S3 access, do not bake credentials into images.
    - Prefer environment variables for small config; use a ConfigMap for non-sensitive settings.

5. Observability
    - Emit logs to stdout/stderr (structured JSON recommended).
    - Emit basic metrics and health signals to the observability stack.

6. Testing at scale
    - Unit test business logic with `unittest.TestCase` and DI for external resources.
    - Add a small integration test that runs the job entrypoint with a local S3 emulator or mocks.

## Quick checklist when adding a new job

- [ ] New file `packages/data_pipeline/jobs/<job_name>.py` created and discovery-safe
- [ ] Exposes `JOB`
- [ ] No heavy import-time side-effects
- [ ] Unit tests added under `packages/data_pipeline/tests/unit`
- [ ] Docker image runs `data-pipeline` as ENTRYPOINT and manifest uses `run <job_name>`
