# ETL Platform Monorepo

This repository houses multiple independently deployable ETL and monitoring modules in a single monorepo.

## Modules

### 1. `etl_core`
- **Purpose**: Pure Python shared utilities for ETL runtimes.
- **Dependencies**: None (Pure Python).
- **Responsibilities**: Config, logging, metrics, S3 utils, retry helpers.

### 2. `file_processing`
- **Purpose**: Combined fileops + data quality runtime lane.
- **Dependencies**: `etl_core`.
- **Responsibilities**: File unzip/decrypt, quarantine, quality analysis.

### 3. `data_pipeline`
- **Purpose**: Combined transforms + ingestion runtime lane.
- **Dependencies**: `etl_core`, `etl-database-schema`.
- **Responsibilities**: S3 transforms, enrichment, backfills, API ingestion.

### 4. `observability`
- **Purpose**: Platform monitoring and health signals.
- **Dependencies**: `etl_core`, `etl-database-schema`.
- **Responsibilities**: S3 metrics, DB metrics, freshness monitors.

## Dependency Management (Poetry)

We use **Poetry** for package management. Each module has its own `pyproject.toml` file in `packages/<module>/`.

- **Path Dependencies**: Modules depend on `etl_core` using path dependencies (e.g., `etl-core = {path = "../etl_core", develop = true}`).
- **External Schema**: `etl-database-schema` is an external dependency containing Django apps and ORM models. It is included as an optional dependency in `data_pipeline` and `observability`.

## Docker Images

We produce separate Docker images for each module. Dockerfiles are located in `docker/`.

| Module | Image Name | Dockerfile |
|---|---|---|
| `file_processing` | `etl-file-processing` | `docker/file-processing.Dockerfile` |
| `data_pipeline` | `etl-data-pipeline` | `docker/data-pipeline.Dockerfile` |
| `observability` | `etl-observability` | `docker/observability.Dockerfile` |

### Building and Running

A `docker-compose.yml` file is provided in `compose/` to build and run all images.

```bash
cd compose
docker-compose up --build
```

## External Schema Integration

The `etl-database-schema` package is referenced as a git dependency in `pyproject.toml` for `data_pipeline` and `observability`.

```toml
etl-database-schema = {git = "https://github.com/example/etl-database-schema.git", branch = "main", optional = true}
```

This allows these modules to be aware of the database schema without tightly coupling the schema definition to this repo.
