# agents.md

# Agent Behavioral Guidelines

## Purpose

This file defines **behavioral rules and decision-making logic** for autonomous agents. These rules control:

- How agents select their mode/role
- What agents must enforce when generating code
- When agents should fetch data, create tests, or refactor
- `etl-platform` is a **Python monorepo** containing multiple independently deployable ETL job modules. Each deployable module builds into its own Docker image and is deployed as batch jobs (EKS/ECS/EMR). This repo is **not** a Django monolith and **not** a web service.

## Scope

- **What's here:** Agent roles, mode selection, enforcement checklists, behavioral guidelines
- **What's NOT here:** Coding standards and patterns (see `copilot-instructions.md` for code style rules)

## Relationship to copilot-instructions.md

- Agents **reference** `copilot-instructions.md` for coding standards
- Agents **follow** `agents.md` for behavioral decisions and enforcement
- Together these files ensure consistent, high-quality code generation.

## Database ownership and repository separation

- Agents must enforce that `etl_core` does not contain domain-specific SQL. `etl_core` may expose a minimal DB client (for example `DatabaseClient.execute_query`) but all business queries or ETL-specific SQL must live in package-level repositories (for example `packages/data_pipeline/repositories`).
- When refactoring or migrating code, agents should move SQL from `etl_core` into the appropriate package repository and update job code to call repository methods.
- Agents should warn in PR descriptions when changes introduce domain SQL into `etl_core` and suggest moving it to a repository module.

## Jobs vs Processors guidance for agents

- Agents generating or refactoring code must follow the `jobs` vs `processors` separation:
  - Jobs live in `packages/data_pipeline/jobs` and must export a top-level `JOB` tuple: `(entrypoint, description)`.
  - Processors live in `packages/data_pipeline/processors` (or `packages/etl_core/processors` if generic) and implement reusable business operations. They accept config dataclasses and client dependencies via constructor injection.
  - Repositories live in `packages/data_pipeline/repositories` and contain domain SQL. They accept a `DatabaseClient` via constructor injection.

- Agents must not place domain SQL in `etl_core` and must not create heavy import-time side-effects in job modules. If an agent detects a migration that would move SQL into `etl_core`, it should automatically propose the code movement and update callers.

- When reporting changes or creating PRs, agents should include a short checklist confirming: job exposes `JOB`, processors accept DI, repositories hold SQL, and `etl_core` contains only generic utilities.

 ## Prohibited layout: `packages/<module>/src/`

- Agents must NOT generate or leave `src/` subdirectories inside packages (for example: `packages/file_processing/src/...`).
- Preferred layout: all Python package sources must live directly under `packages/<module>/` (for example `packages/file_processing/<package files>`).
- If agents encounter an existing `src/` layout during generation, they must:
  1. Avoid creating new files inside the `src/` tree.
  2. Propose and optionally apply a refactor that moves source files from `packages/<module>/src/<module>/...` to `packages/<module>/...`, adjusting imports accordingly.
  3. Include a PR note explaining the refactor and confirming that tests and imports were validated.

- Agents should also add a hint in their PR that CI should run an import/pytest smoke to ensure no import-path regressions were introduced.

---

# Global Agent Rules

These rules apply to all agents.

- Keep responses concise and actionable.
- Output full runnable files unless diffs are requested.
- Follow all coding, testing, and documentation standards defined in `copilot-instructions.md`.
- Never hallucinate directories, imports, APIs, commands, or file names.
- Ask for clarification only when necessary to avoid incorrect output.
- Automatically select the correct agent role based on file path, file type, or user intent.

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
a
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

## Standalone modules using ORM models
- If a module imports `etl-database-schema` models, it acts as a Django project runner. The agent must ensure a minimal `settings.py` exists in the package (configuring INSTALLED_APPS/DATABASES) and is used to bootstrap Django in the entrypoints.

## Module inventory
- `packages/etl_core`: shared utilities (config/logging/metrics/S3/retry/types). No Django.
- `packages/file_processing`: decrypt/unzip/materialize + whole-file quality analysis.
- `packages/data_pipeline`: transforms + ingestion (S3 transforms + application API ingestion).
- `packages/observability`: S3/DB metrics + DB monitoring checks + freshness/latency.

## Packaging expectations
- Each module is a separate Poetry project under `packages/<module>/`.
- Each module maintains its own `poetry.lock` for reproducible builds.

## Containerization expectations
- One Dockerfile per deployable module (under `docker/`).
- Each image installs only:
   - that module
   - `etl_core` (path dependency)
   - `etl-database-schema` only if the module requires it

## Infra and new-module enforcement

- Foundation prerequisite: ensure `infra/plumbing` (foundation_network) is applied once per environment before generating module-level infra. Do not inline foundation networking into module stacks.
- Per-module infra pattern: create or update `infra/<module>/` with its own Terraform and `scripts/manage.sh` helper (init/plan/apply/destroy/update-image as applicable). Avoid reusing another module's Terraform; create their own stack that consumes the foundation outputs or explicitly passed VPC/subnet ids.
- LocalStack/local helpers: place shared localstack utilities in `infra/local`; add module-specific local scripts under `infra/<module>/scripts` (e.g., `setup_localstack.sh`, `ecr_put.sh`, `manage.sh`) instead of new ad-hoc locations. Agents generating infra must ensure these helper scripts exist (or update README explaining differences) so local development and CI can run consistently.
- Dockerfiles: require one Dockerfile per deployable module under `docker/<module>.Dockerfile`. Images must install only that module plus `etl_core` (and `etl-database-schema` if needed). Never build from repo root.
- Module scaffolding: every new `packages/<module>/` must include `pyproject.toml`, `poetry.lock`, and package sources at the package root (no `src/` layout). Do not add cross-module imports beyond `etl_core`.
- Jobs/processors/repos still apply: jobs orchestrate, processors hold business logic, repositories hold SQL. Infra additions must not move domain SQL into `etl_core`.
- Put reusable, domain-agnostic utilities (e.g., circuit breakers, generic executors, shared config loaders) in `etl_core/support`. Keep domain-specific configs (like `SeederConfig`) in the owning package.

## ORM consumption alignment (etl-database-schema)
- Two allowed patterns; agents must choose per module and enforce consistently:
  1) Optional ORM: wrap `etl_database_schema` imports in `try/except` and fall back to SQL if Django is not configured (no implicit django.setup). Do not fail the job if Django settings are absent. This matches file_processing monitoring repository behavior.
  2) Required ORM: demand `DJANGO_SETTINGS_MODULE` and run `django.setup()` via a bootstrap helper before model access. Fail fast with a clear error if settings/DB env are missing. This matches reporting_seeder behavior.
- Never mix patterns inside one module. If ORM is required, do not keep silent fallbacks; if ORM is optional, do not import models at module import time.

## Environment sourcing alignment
- Local/CLI: rely on `etl_core.cli.main_for_package()` to load `<package>/.env` into the process without overriding existing env vars.
- Kubernetes: require env injection via ConfigMap/Secret (`envFrom`), not inline secrets. Keep variable names aligned with `.env` for parity across modules.
- Agents should update manifests to remove inline secrets and prefer ConfigMap/Secret, and ensure optional-ORM modules can run without Django-specific env when ORM is disabled.
