# ETL Platform Monorepo

This repository contains multiple independently deployable ETL and monitoring modules organized as a monorepo.
The top-level README is intentionally high-level — each module (and infra stack) has its own README and deployment docs.

Quick links
- packages/: module source and package-level README files
- infra/: infrastructure stacks and per-module deployment guides (see `infra/README.md`)
- docs/airflow/: Airflow-specific deployment and operational docs

Modules

1. `etl_core`
- Purpose: Pure Python shared utilities for ETL runtimes (config, logging, metrics, S3 helpers, retry helpers).
- Dependencies: None (pure Python).

2. `file_processing`
- Purpose: File operations + data quality and profiling runtime.
- Dependencies: `etl_core`.

3. `data_pipeline`
- Purpose: Transforms, enrichment and ingestion jobs.
- Dependencies: `etl_core`, `etl-database-schema` (optional).

4. `observability`
- Purpose: Platform monitoring and freshness/health checks.
- Dependencies: `etl_core`, `etl-database-schema` (optional).

Packaging & dependencies

- Each package under `packages/<name>/` is a self-contained Python package with its own `pyproject.toml` (Poetry-managed).
- `etl_core` is used as a path dependency by other packages.
- Do NOT add a `src/` layout inside packages; package sources live at the package root.

Container images & local compose

- Separate container images are produced per package. Dockerfiles live under `docker/` or inside package folders where noted.
- The `compose/` folder provides a local development composition (see `compose/README.md`).

Airflow control plane (high level)

This repository includes an Airflow "control plane" component that generates and distributes DAGs for package-level jobs. The project follows a modular deployment model: packages are deployable independently and execute their job code inside their own container images.

Key principles (summary)
- DAGs are treated as deployment artifacts generated and published by the owning package's CI pipeline.
- The running Airflow Scheduler/Webserver remain long-lived and discover DAGs from a shared DAG location — no control-plane image rebuild is required when packages add jobs.
- Generated DAGs reference package container images (KubernetesPodOperator) so runtime execution is isolated from the scheduler.

DAG distribution contract (canonical layout)

Packages publish DAG artifacts to a shared S3 bucket using the following layout:

s3://<dag-bucket>/<env>/<package_name>/
├── dags/
│   └── <dag_id>.py
└── metadata.json   # optional, package-level info (schedules, resources)

Rules and guardrails
- Packages may only write to their own S3 prefix (no cross-package writes).
- DAG IDs must be globally unique.
- DAG files must be deterministic and idempotent.
- DAGs should use `KubernetesPodOperator` to run the package image — the scheduler does not require package source code.

CI integration (package responsibility)

Each package CI pipeline should:
- Build/package the image for the package (IMAGE_TAG).
- Run a DAG generator (or template) that emits deterministic DAG files.
- Upload DAG files to `s3://<dag-bucket>/<env>/<package_name>/dags/` and any optional `metadata.json`.

Required environment variables for the CI step (example):
- ENV
- PACKAGE_NAME
- IMAGE_TAG
- DAG_BUCKET

Airflow control plane runtime (deployment responsibility)

- The Airflow deployment mounts a DAG directory (e.g., `/opt/airflow/dags`) and runs a lightweight sync sidecar or init process that mirrors the S3 DAG prefix into that directory.
- The sidecar must perform safe, read-only syncs (no in-place partial writes) and ensure atomic updates (write to temp + rename).
- Airflow discovers DAGs via its normal parsing cycle (no custom scheduler or external registration required).

Recommended settings (example)
- `dags_folder`: /opt/airflow/dags
- `dag_dir_list_interval`: tuned to expected update cadence (e.g., 300s)
- Sidecar sync interval: consistent with `dag_dir_list_interval` (e.g., every 60–300s)

DAG authoring pattern (reference)

- Use `KubernetesPodOperator` to run the package image.
- Accept runtime config cleanly via `dag_run.conf` or Airflow Variables.
- Explicitly set retries, SLA, resource limits, namespace, and image pull policy.
- Do not import or assume package source code exists in the scheduler image.

Operational notes

- On DAG upload failure: package CI should fail the pipeline and alert; Airflow continues running existing DAGs.
- Malformed DAGs: DAG files must be validated in CI to avoid breaking the scheduler parse cycle.
- Blast radius: store each package's DAGs under its own prefix to allow per-package rollback and isolation.
- Rollback: package CI should support removing or replacing DAG files (for example, upload a previous DAG artifact) and optionally call the Airflow REST API to unpause or trigger a smoke run.

Where to find more details
- Full control-plane design and operational details: `AIRFLOW_CONTROL_PLANE_SUMMARY.md` (in repo root).
- Airflow infra manifests and deployment notes: `infra/airflow_control_plane/README.md` and `docs/airflow/DEPLOYMENT.md`.
- Per-package CI examples and DAG generator templates: see `packages/<package>/` README and CI config in each package.

Contributing and developer workflow

- Jobs should be added under the owning package following the package's README and job conventions.
- Package CI must validate DAG generation and upload; control-plane image rebuilds must not be relied upon for DAG discovery.
- For local development, the `compose/` setup can mount sources for faster iteration.

License & governance

Repository-level license and contributor guidelines are available at the repository root.
