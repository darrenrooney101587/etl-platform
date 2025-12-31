# ETL Platform – Context and Structural Goals

## Purpose of this Document
This document captures the **architectural intent and structural goals** for the `etl-platform` repository, specifically to guide automated agents (Codex / Copilot) when restructuring the `packages/data_pipeline` module.

If something is ambiguous during refactoring, **this document takes precedence** over inferred structure from legacy code.

---

## What `etl-platform` Is
`etl-platform` is a **Python monorepo** that contains multiple **independently deployable ETL job modules**, each built into its own Docker image and deployed as batch jobs (EKS / ECS / EMR).

This repo is **not** a Django monolith and **not** a web application.

---

## Core Architectural Principles

### 1. Jobs, not services
- Modules in `etl-platform` represent **jobs / pipelines**, not long-running web servers.
- No module should behave like a Django web app.
- Entry points are **CLI commands**, not HTTP endpoints.

### 2. One Python package namespace per module
- Each module lives under:
  ```
  packages/<module_name>/src/<module_name>/
  ```
- There must be exactly **one import namespace** per module.
- Example:
  ```python
  import data_pipeline
  ```

---

## Module Responsibilities

### `etl_core`
- Shared **pure Python** utilities.
- Examples:
  - logging
  - metrics helpers
  - S3 helpers
  - retry/backoff
  - config helpers
- **Must not import Django**
- **Must not import database models**

---

### `data_pipeline` (current focus)
- Combines **data transforms + ingestion**
- Runs as batch jobs or scheduled tasks
- May:
  - read/write S3
  - call application APIs
  - optionally use Django ORM **via external schema package**

#### What `data_pipeline` is NOT
- Not a Django project
- Not a Django app
- Not a web service

---

## Django Usage Model (Critical)

### External schema dependency
- Django ORM models and migrations live in:
  **`etl-database-schema`** (external repo/package)
- `data_pipeline` may depend on this package **only if needed**
- Django is treated as a **library**, not a framework

### Forbidden inside `data_pipeline`
The following must **not** exist in the active package namespace:
- `manage.py`
- `settings.py`
- `wsgi.py` / `asgi.py`
- `urls.py`
- `views.py`
- `apps.py`
- `management/commands/`

If legacy Django files exist, they must be:
- moved to `packages/data_pipeline/legacy_django/`, or
- removed after verification

---

## Intended `data_pipeline` Structure

Final desired structure:

```
packages/data_pipeline/
  pyproject.toml
  README.md
  legacy_django/          # quarantined legacy Django project (inactive)
  src/
    data_pipeline/
      __init__.py
      cli/                # CLI entrypoints (former Django management commands)
      config/
      database/
      processors/
      s3/
      support/
  tests/
```

### CLI Entry Points
- All runnable behaviors must be exposed as **CLI commands**
- Former Django management commands must be converted into:
  ```
  src/data_pipeline/cli/<command>.py
  ```
- Exposed via Poetry `console_scripts`

Example (conceptual only):
```toml
[tool.poetry.scripts]
data-pipeline-get-s3-files = "data_pipeline.cli.get_s3_files:main"
```

---

## Migration & Refactor Rules

### Allowed
- File moves
- Import path updates
- Packaging changes
- Converting Django commands to CLI scripts
- Minimal bootstrap code to remove Django dependency

### Not allowed
- Rewriting business logic
- Introducing new abstractions
- Creating new Django apps/projects
- Reintroducing `manage.py`

---

## Success Criteria (Agent Checklist)

An agent has succeeded when:
- `packages/data_pipeline/src/data_pipeline/` contains **only non-Django code**
- There is **one** `data_pipeline` Python package
- Django artifacts are quarantined or removed
- `poetry install` works for `data_pipeline`
- At least one CLI entrypoint replaces legacy Django command usage
- The structure matches the intent described above

---

## Agent Instruction
When restructuring `packages/data_pipeline`, **opt for mechanical changes only** and preserve runtime behavior.

If a decision is unclear:
> Prefer removing Django framework structure over preserving it.

This repo is an ETL **job platform**, not a Django application.
