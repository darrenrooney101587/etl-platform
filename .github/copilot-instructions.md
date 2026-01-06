# Copilot Instructions — `etl-platform`
# Copilot Coding Instructions

## Purpose

This file defines **coding standards and patterns** for the repository. These rules apply to:

- General AI chat interactions
- Agent-based code generation
- Human developers writing code

---

These instructions define the **coding standards** for this repository.
All generated code must follow these rules.
Behavioral logic (how agents respond and make decisions) is defined in `agents.md`.

---


# 1. General Standards

- Keep output concise and focused on the requested task.
- No emojis in code, comments, logs, or documentation.
- Comments should explain non-obvious logic only.
- Never hallucinate folders, file names, functions, models, components, or imports.
- All imports must be at the top of each file.

# 2. Python / Django Standards

## 2.1 Core Rules

- Python version: **3.10**
- Follow **PEP‑8** for style and formatting.
- Use **PEP‑287** docstrings for all modules, classes, methods, and functions.
- Use **complete type annotations** everywhere.
- Use **exceptions**, not return codes, for error handling.
- Prefer **class-based design** for application logic.

## 2.2 Imports

Order imports in three groups:

1. Standard library
2. Third-party
3. Local modules
   Each group must be alphabetized.

## 2.3 Dependency Injection

All classes that talk to external resources (AWS, HTTP clients, DB connectors, registries, etc.) must:

- Accept dependencies via constructor injection.
- Default to production implementations.
- Allow test injection for mocking.


## 2.5 Database separation rule

- `etl_core` must not contain domain-specific SQL queries or Django ORM models. It may provide a minimal, DI-friendly DB client (for example `DatabaseClient.execute_query`) that exposes a simple query execution surface returning dict rows.
- All business-domain SQL (reports, extracts, ETL-specific SELECTs) must live in package-level repositories (for example `packages/data_pipeline/repositories`), not in `etl_core`.
- Repositories should accept a `DatabaseClient` via constructor injection and expose named methods (e.g. `get_attachment_files_for_s3_processing`) that return typed results.
- If a query becomes broadly useful across modules or should be kept as canonical domain logic, promote it to `etl-database-schema` or another shared schema package.

## 2.4 Testing

- Use **unittest.TestCase** for all tests.
- Include a `if __name__ == "__main__": unittest.main()` block.
- Use DI to mock all external resources.
- Each Django app stores tests in its own `tests/` directory.

## Hard rules
1.  **Keep Django out of `etl_core`**
    - `etl_core` must not import Django or `etl-database-schema`.

3. **Per-module Poetry projects**
    - Each module under `./packages/<name>` has:
        - `pyproject.toml`
        - `poetry.lock`
    - Dependencies are scoped per module. Do not add heavy deps globally.

## Package layout: no `src/` subdirectory

- Rule: Do NOT create a `src/` layout inside package modules. All package python source must live at the package root under `packages/<name>/` (for example `packages/file_processing/<python package modules>`), not under `packages/<name>/src/<name>`.
- Rationale: Our build, packaging, and path-resolution conventions expect package modules to be the top-level directory under `packages/`. The `src/` layout introduces unnecessary import complexity, deviates from repo conventions, and causes tooling mistakes when generating code.
- Author guidance:
  - When creating a new package under `packages/`, place the package module files directly at `packages/<name>/<module>.py` or `packages/<name>/<pkg>/__init__.py`.
  - Ensure `pyproject.toml` and `poetry.lock` remain at the package root (`packages/<name>/`).
  - Avoid creating `packages/<name>/src/` or adding `sys.path` hacks to compensate for the `src/` layout.
- Agent enforcement:
  - Agents must not generate new packages using a `src/` subdirectory.
  - If an agent detects an existing `src/` layout during generation or refactor, it should either: (a) place new code at the package root instead, or (b) refactor the layout by moving sources to the package root and updating imports. Agents should surface a clear PR note describing the refactor.
  - CI checks should flag new `src/` directories inside `packages/` as policy violations.

6. **No Django project structure inside job modules**
    - Do not create/keep `manage.py`, `settings.py`, `wsgi.py`, `urls.py`, `views.py`, `apps.py`, `management/commands` inside active module packages.
    - Convert legacy Django management commands into CLI entrypoints under `./packages/<module>/cli/`.

## Engineering expectations
- When touching function signatures, add type hints (minimal).
- Avoid introducing new abstractions during migration.
- Keep operational scripts explicit and readable.

## Testing

- Use **unittest.TestCase** for all tests.
- Include a `if __name__ == "__main__": unittest.main()` block.
- Use DI to mock all external resources.

## Jobs vs Processors (for authors and agents)

- Purpose: Make the runtime separation explicit so code, tests, and automated agents follow the same conventions.

- Jobs (`packages/data_pipeline/jobs`):
  - Orchestration and operational surface only.
  - Responsibilities: parse CLI args, wire configs/repositories/processors, perform high-level error handling, map to exit codes and logs.
  - MUST NOT contain domain SQL or heavy data access logic. Use DI to accept repository and processor instances.
  - Discovery contract: job modules MUST export a top-level `JOB` tuple: `(entrypoint, description)` where `entrypoint(argv: List[str]) -> int`.

- Processors (`packages/data_pipeline/processors` or `packages/etl_core/processors`):
  - Focused reusable business logic (S3 file transforms, CSV creation, data shaping).
  - Accept typed `config` dataclasses and client dependencies via constructor injection.
  - Return plain Python structures (dict/list) and raise exceptions for unexpected failures.
  - Keep side-effects explicit and idempotent where possible.

- Repositories (`packages/data_pipeline/repositories`):
  - Contain domain SQL and data-shaping logic; accept a `DatabaseClient` via constructor injection.
  - `etl_core` must NOT contain business SQL — it may provide only a minimal `DatabaseClient.execute_query`.

- Tests and agents:
  - Unit tests should inject fakes/mocks for external resources (DB, S3) using `unittest.TestCase`.
  - Agents must enforce this separation: when moving or generating code, place domain SQL in repositories, business operations in processors, and orchestration in jobs.
