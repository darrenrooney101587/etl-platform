# ETL Platform Monorepo

This repository contains multiple independently deployable ETL and monitoring modules organized as a monorepo.
The top-level README is intentionally high-level — each module (and infra stack) has its own README and deployment docs.

Quick links
- packages/: module source and package-level README files
- infra/: infrastructure stacks and per-module deployment guides
- docs/airflow/: Airflow-specific deployment and operational docs
- AIRFLOW_CONTROL_PLANE_SUMMARY.md: detailed control-plane design and implementation notes

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

- We build separate container images per package. Dockerfiles live under `docker/` or inside package folders where noted.
- A `compose/` folder provides a simple local development composition (see `compose/README.md`).

Airflow control plane (high level)

This repository contains an Airflow "control plane" component that generates and distributes DAGs for package-level jobs. The project follows a modular deployment model: packages are deployable independently and run their job code inside their own container images.

Key principles (summary)
- DAGs are treated as deployment artifacts and must be generated and published by the owning package's CI pipeline.
- The running Airflow Scheduler/Webserver remain long-lived and discover DAGs from a shared DAG location — no control-plane image rebuild is required when packages add jobs.
- Generated DAGs must reference package container images (KubernetesPodOperator) so runtime execution is isolated from the scheduler.

DAG distribution contract (canonical layout)

Packages must publish DAG artifacts to a shared S3 bucket using the following layout:

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

Each package CI should:
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

- If DAG upload fails: CI should fail the pipeline and alert; Airflow will continue running existing DAGs.
- Malformed DAGs: keep DAG files small and validate syntax in CI before upload to avoid breaking the scheduler parse cycle.
- Blast radius: store each package's DAGs under its own prefix to allow per-package rollback and isolation.
- Rollback: CI should support removing or replacing DAG files (e.g., upload previous DAG artifact) and optionally trigger Airflow REST API to unpause or trigger a smoke run.

Where to find more details
- Full control-plane design and operational details: `AIRFLOW_CONTROL_PLANE_SUMMARY.md` (in repo root).
- Airflow infra manifests and deployment notes: `infra/airflow_control_plane/README.md` and `docs/airflow/DEPLOYMENT.md`.
- Per-package CI examples and DAG generator templates: look at `packages/<package>/` README and CI config in each package.

Contributing and developer workflow

- Add jobs under your package following the package's README and job conventions.
- Validate DAG generation and upload in your package CI; do not rely on pushing changes to the control-plane image.
- For local development use `compose/` and package-level scripts — the compose setup may mount sources for faster iteration.

License & governance

See the repository root for license and contributor guidelines.
