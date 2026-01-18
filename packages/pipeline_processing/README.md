# pipeline_processing

Pipeline processing package combining transforms, ingestion, data quality validation, and file processing.

## Responsibilities

- S3‑based transforms (bronze → silver)
- Enrichment & normalization
- Backfills / reprocessing
- Application API ingestion
- Data quality validation and profiling
- File processing and monitoring
- Idempotency, batching, DLQ, audit trails

## Package History

This package is the result of merging two packages:
- `data_pipeline` - Combined transforms + ingestion runtime lane
- `file_processing` - Data quality validation and file processing pipeline

Both packages have been consolidated into `pipeline_processing` to better reflect the high-level data engineering concerns alongside other major facets (observability, orchestration, etl_core).

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

- `pipeline-processing` → general module entrypoint (configured as the image ENTRYPOINT in our Dockerfile).
- `pipeline-processing-get-s3-files` → specific job CLI that runs the S3 file processing flow.

Preferred production run (ENTRYPOINT set to console script)

```bash
# Image must be built so the console script is installed and available as the ENTRYPOINT.
# The Job only passes arguments to the container.
docker run --rm etl-pipeline-processing \
  --agency-id 10 \
  --source-bucket benchmarkanalytics-production-env-userdocument-test \
  --destination-bucket etl-ba-research-client-etl
```

Fallback production run (explicit invocation)

```bash
# If the image does not set ENTRYPOINT, invoke the console script explicitly.
docker run --rm etl-pipeline-processing \
  pipeline-processing-get-s3-files --agency-id 10 \
  --source-bucket benchmarkanalytics-production-env-userdocument-test \
  --destination-bucket etl-ba-research-client-etl
```

Developer workflow (mount source, auto-install deps)

```bash
# Mount local source into the container and use the dev entrypoint which
# will install dependencies if necessary. This is for iterative development.
docker run --rm -it \
  -v "$(pwd)/packages/pipeline_processing:/app/packages/pipeline_processing" \
  -v "$(pwd)/packages/etl_core:/app/packages/etl_core" \
  --workdir /app/packages/pipeline_processing \
  --entrypoint /app/packages/pipeline_processing/config_scripts/docker-entrypoint.sh \
  etl-pipeline-processing \
  poetry run pipeline-processing-get-s3-files --agency-id 10
```

Set environment variable `SKIP_INSTALL=1` when dependencies are already present and the install step should be skipped.

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
          image: ghcr.example.com/your-org/etl-pipeline-processing:latest
          # Preferred: set the image ENTRYPOINT to the console script and pass args only
          command: [ "pipeline-processing" ]
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
- If there is a need to run without an installed console script, the module
  can be run with Python: `python -m data_pipeline.cli.get_s3_files --help`.

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

- Parallelism / batching: if concurrent processing of many agencies is required, create a controller/job-generator that
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

## Jobs vs Processors — conceptual separation

When developing in `packages/data_pipeline`, two primary abstractions are used: "jobs" and "processors". Keeping the distinction clear improves testability, ownership, and scale.

- Job (location: `packages/data_pipeline/jobs`)
  - Purpose: orchestration and operational concerns. A job wires together configuration, repositories, processors, and adapters; it parses CLI args, composes resources, and maps results to exit codes and human-friendly output.
  - Characteristics:
    - Small module with a single public entrypoint (see `JOB = (entrypoint, description)` convention).
    - Responsible for CLI parsing, high-level error handling, logging, and progress reporting.
    - Does not contain business-domain SQL or low-level data access logic.
    - Accepts dependencies via constructor injection (DB client, S3 client, repositories) for testability.
  - Example responsibilities:
    - Constructing an `S3Config` and a configured S3 processor adapter.
    - Calling `AttachmentRepository.get_attachment_files_for_s3_processing(agency_id)`.
    - Calling processor methods to copy files and upload metadata.
    - Aggregating results and returning a process exit code.

- Processor (location: `packages/data_pipeline/processors` or `packages/etl_core/processors`)
  - Purpose: encapsulate focused, reusable business logic and operations (for example: S3 file copying, employment history CSV creation and upload).
  - Characteristics:
    - Implemented as classes or small modules with clear public methods (for example `process_files`, `fetch_data`, `upload_to_s3`).
    - Accept dependencies through the constructor (S3 client, DB client, configuration dataclass).
    - Can be reused by multiple jobs and by higher-level orchestrators.
    - Keep side effects explicit: methods that perform side effects (S3 upload, DB writes) should be separate from read-only helpers.
  - Example responsibilities:
    - Given a list of file mappings, perform copies and return a list of per-file results.
    - Given an agency id, fetch employment history rows and format them as CSV-ready dicts.

- Why this separation helps

  - Testability: processors are easy to unit test by injecting fake S3/DB clients; jobs can be tested by injecting fake processors and repositories.
  - Ownership: domain SQL and data-shaping lives in package-level repositories (e.g. `packages/data_pipeline/repositories`) instead of `etl_core` (which stays generic).
  - Reuse: processors implement mechanics once and are used by many jobs (reduces duplication).
  - Operations: Jobs remain thin and focus on logging, retries policy, and mapping to orchestration systems (K8s exit codes, metrics), making them safer to run at scale.

- Contract (how to design a processor)

  - Inputs: simple typed values or dataclasses (e.g. `S3Config`, `EmploymentHistoryConfig`) and dependency objects (clients/adapters).
  - Outputs: plain Python types (dicts, lists) describing results or summaries. Avoid returning framework-specific types.
  - Error handling: processors should raise exceptions for unexpected failures and return structured result dicts for expected outcomes (for example a per-file status row). Jobs should catch exceptions and decide whether to retry, warn, or fail the whole job.
  - Idempotency: where possible, make processor operations idempotent (so retries are safe).

Edge cases to consider

- Empty inputs (no files / no employment rows) — processors should return clear "no-op" results, not throw.
- Partial failures — processors should return per-item status so the job can continue processing other items and report failures.
- Timeouts / retries — keep retry behaviour small and configurable on the processor via config.

Testing guidance

- Unit tests for processors: inject fake clients (S3, DB) and assert method outputs. Use `unittest.TestCase` and keep tests fast.
- Unit tests for jobs: inject fake processors/repositories and assert the job parses args, calls the correct methods, and returns expected exit codes and printed output.
- Integration tests: run a job entrypoint with a test Postgres or S3 emulator (optional for CI).

Quick checklist for adding a Processor

- [ ] Add class under `packages/data_pipeline/processors` (or `etl_core/processors` if generic)
- [ ] Accept `config` dataclass + client dependencies in constructor
- [ ] Keep public methods small and side-effects explicit
- [ ] Add unit tests in `packages/data_pipeline/tests/unit`
- [ ] Document the processor in the job README if it is job-specific
