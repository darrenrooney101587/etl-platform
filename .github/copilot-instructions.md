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

4. **Root Poetry is workspace-only**
    - Root `pyproject.toml` is for dev tooling and editable path deps.
    - **Never** build containers from the root project.
    - Dockerfiles must install from the module directory using that module's lock.

5. **`etl-database-schema` dependency model**
    - Treat `etl-database-schema` as an external package (Git URL or internal index).
    - Prefer making it an optional dependency group inside the module.

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
