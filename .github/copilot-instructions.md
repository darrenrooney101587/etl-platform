# Copilot Instructions — `etl-platform`

## Goal
Assist in restructuring and maintaining a Python monorepo with multiple deployable modules and images, using Poetry and strong dependency boundaries.

## Mandatory Rules
1. **No business logic changes unless required for packaging/runtime**
   - Prefer “mechanical” refactors: move files, adjust imports, update configs.
   - If behavior must change, document it explicitly.

2. **Keep Django out of `etl_core`**
   - `etl_core` must not import Django or `etl-database-schema`.

3. **Use Poetry per module**
   - Each module under `packages/<name>` has its own `pyproject.toml`.
   - Use `src/` layout and explicit package includes.

4. **`etl-database-schema` usage**
   - Treat `etl-database-schema` as an external dependency (Git URL or internal index).
   - Only `data_pipeline` and `observability` should depend on it by default.
   - `file_processing` should avoid it unless absolutely unavoidable.

5. **Multi-image Docker build**
   - One Dockerfile per deployable module:
     - `docker/file-processing.Dockerfile`
     - `docker/data-pipeline.Dockerfile`
     - `docker/observability.Dockerfile`
   - Images should install only what they need.

6. **Compose**
   - `compose/docker-compose.yml` builds and runs all images with placeholder commands if needed.

## Migration Instructions (Legacy repo → `packages/data_pipeline`)
When migrating `etl-data-extraction` into `packages/data_pipeline`:
- Preserve legacy application behavior and CLI/entrypoints where possible.
- Refactor into the `src/data_pipeline/` package.
- Ensure imports are updated to match the new package name and layout.
- Split config, manifests, and runtime scripts into appropriate locations without rewriting core algorithms.

## Style / Engineering Expectations
- Add type hints when touching function signatures (minimal, do not refactor extensively).
- Avoid “clever” abstractions during migration.
- Keep operational scripts explicit and readable.
