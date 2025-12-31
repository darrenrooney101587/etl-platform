# Agents.md — `etl-platform` Monorepo Guidance

## Purpose
This repository is a **single monorepo** containing multiple independently deployable Python modules and Docker images. Agents working in this repo must preserve clear boundaries between modules, packaging, and deployment artifacts.

## Core Principles
1. **Deploy images, not repos**
   - Kubernetes/ECS runs container images. Each module builds to its own image.

2. **Strong module boundaries**
   - Modules may share code only through `packages/etl_core`.
   - Avoid cross-imports between sibling modules (`file_processing`, `data_pipeline`, `observability`) unless explicitly approved.

3. **No Django in `etl_core`**
   - `etl_core` must remain **pure Python** (no Django settings, no ORM imports).

4. **External schema dependency**
   - Database models and migrations live in a separate package: **`etl-database-schema`**.
   - Only modules that truly require schema awareness may depend on it (typically `data_pipeline` and `observability`).

5. **Separate resource lanes**
   - `file_processing` is IO + scratch heavy.
   - `data_pipeline` is compute + side-effects (API writes).
   - `observability` is lightweight + scheduled.
   - Keep these lanes separate in images and deploy configurations.

## Module Inventory
- `packages/etl_core`: shared utilities only (config/logging/metrics/S3/retry/types)
- `packages/file_processing`: decrypt/unzip/materialize + whole-file quality analysis
- `packages/data_pipeline`: transforms + ingestion (S3 transforms + application API ingestion)
- `packages/observability`: S3/DB metrics + DB monitoring checks + freshness/latency

## Repository Layout Expectations
- Each module is a separate Poetry project under `packages/<module>/`
- Each module uses `src/` layout
- Each module has its own Dockerfile under `docker/`
- Compose file builds all module images under `compose/docker-compose.yml`

## Migration / Refactor Guidance
When migrating legacy repos into `etl-platform`:
- Preserve behavior first; refactor structure second.
- Convert legacy entrypoints into module-local CLI/runner entrypoints.
- Add minimal shims to keep existing runtime invocations working (do not redesign business logic during migration unless required).
- Move shared helpers into `etl_core` only after migration is stable.

## Quality Bar
- Changes must be consistent with module boundaries and packaging rules.
- Avoid introducing new dependencies globally; keep them per-module.
- Document non-obvious decisions in module READMEs.
