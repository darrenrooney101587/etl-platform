# Agents.md — `etl-platform` Monorepo Guidance

## Purpose
`etl-platform` is a **Python monorepo** containing multiple independently deployable ETL job modules. Each deployable module builds into its own Docker image and is deployed as batch jobs (EKS/ECS/EMR). This repo is **not** a Django monolith and **not** a web service.

## Non-negotiable rules
1. **Deploy images, not repos**
   - EKS/ECS runs container images. Each module builds to its own image.

2. **Module boundaries**
   - Shared code is allowed **only** via `./packages/etl_core`.
   - Avoid cross-imports between sibling modules (`file_processing`, `data_pipeline`, `observability`) unless explicitly approved.

3. **No Django in `etl_core`**
   - `etl_core` must remain **pure Python**:
      - no Django imports
      - no ORM imports
      - no settings/migrations

4. **Schema package is external**
   - Django ORM models and migrations live in an external package:
      - **`etl-database-schema`**
   - Modules may depend on it **only** if they require schema awareness (usually `data_pipeline` and `observability`).

5. **No Django project artifacts inside job modules**
   - Job modules are not Django projects. Do not create or preserve:
      - `manage.py`, `settings.py`, `wsgi.py/asgi.py`, `urls.py`, `views.py`, `apps.py`, `management/commands`
   - If legacy Django artifacts exist, quarantine under `legacy_django/`.

6. **Root Poetry is workspace-only**
   - Root `pyproject.toml` exists for **local development/tooling only** (`package-mode=false`).
   - **Docker builds must never install from the repo root**.
   - Dockerfiles must install from each module directory (module `pyproject.toml` + `poetry.lock`).

## Module inventory
- `packages/etl_core`: shared utilities (config/logging/metrics/S3/retry/types). No Django.
- `packages/file_processing`: decrypt/unzip/materialize + whole-file quality analysis.
- `packages/data_pipeline`: transforms + ingestion (S3 transforms + application API ingestion).
- `packages/observability`: S3/DB metrics + DB monitoring checks + freshness/latency.

## Packaging expectations
- Each module is a separate Poetry project under `packages/<module>/`.
- Each module uses `src/` layout.
- Each module maintains its own `poetry.lock` for reproducible builds.

## Containerization expectations
- One Dockerfile per deployable module (under `docker/`).
- Each image installs only:
   - that module
   - `etl_core` (path dependency)
   - `etl-database-schema` only if the module requires it
