# Copilot Instructions — `etl-platform`

## Goal
Maintain a Python monorepo with multiple deployable job modules and images, using Poetry and strict dependency boundaries.

## Hard rules
1. **Do not redesign business logic**
    - Prefer mechanical refactors: file moves, import updates, configuration wiring.
    - If behavior must change for packaging/runtime, document it.

2. **Keep Django out of `etl_core`**
    - `etl_core` must not import Django or `etl-database-schema`.

3. **Per-module Poetry projects**
    - Each module under `packages/<name>` has:
        - `pyproject.toml`
        - `poetry.lock`
        - `src/<name>/...`
    - Dependencies are scoped per module. Do not add heavy deps globally.

4. **Root Poetry is workspace-only**
    - Root `pyproject.toml` is for dev tooling and editable path deps.
    - **Never** build containers from the root project.
    - Dockerfiles must install from the module directory using that module's lock.

5. **`etl-database-schema` dependency model**
    - Treat `etl-database-schema` as an external package (Git URL or internal index).
    - Only `data_pipeline` and `observability` should depend on it by default.
    - Prefer making it an optional dependency group inside the module.

6. **No Django project structure inside job modules**
    - Do not create/keep `manage.py`, `settings.py`, `wsgi.py`, `urls.py`, `views.py`, `apps.py`, `management/commands` inside active module packages.
    - Convert legacy Django management commands into CLI entrypoints under `src/<module>/cli/`.

## Migration instructions: legacy Django-style repo → `packages/data_pipeline`
- Preserve the working application behavior, but remove Django project scaffolding.
- Keep functional code under `src/data_pipeline/` (s3/database/processors/config/support).
- Convert `management/commands/*` into `src/data_pipeline/cli/*` and expose with Poetry console scripts.
- Quarantine leftover Django project artifacts under `packages/data_pipeline/legacy_django/`.

## Engineering expectations
- When touching function signatures, add type hints (minimal).
- Avoid introducing new abstractions during migration.
- Keep operational scripts explicit and readable.
