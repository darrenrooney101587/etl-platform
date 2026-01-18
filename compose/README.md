# Compose development runbook

This repo uses a monorepo layout where each package lives under `packages/`.

Important: docker-compose commands should be executed from the repository root so the compose build `context: ../` resolves to the repo root and Dockerfile COPY paths like `packages/...` succeed.

Quick commands (run from repo root):

Build and start the whole stack (rebuild images):

```bash
cd /path/to/etl-platform
docker-compose -f compose/docker-compose.yml up -d --build
```

Build only a specific service (useful for debugging):

```bash
docker-compose -f compose/docker-compose.yml build pipeline-processing
# or run with build and show logs
docker-compose -f compose/docker-compose.yml up --build pipeline-processing
```

Package-local helpers

Each package includes a small `build.sh` helper that builds its image using the repository root as the Docker build context. This avoids confusion about where to run `docker build`.

Example:

```bash
# from anywhere
packages/observability/build.sh
packages/pipeline_processing/build.sh
packages/reporting_seeder/build.sh
```

If a package requires private git dependencies at build time, the following options are recommended:
- Generate and commit a `poetry.lock` for the package so the build does not need to resolve git+ssh references.
- Use BuildKit and forward an SSH agent when building (CI or a secure host):

```bash
DOCKER_BUILDKIT=1 docker build --ssh default -t my-image -f packages/<pkg>/<pkg>.Dockerfile /path/to/repo
```

Notes

- The compose file intentionally uses `context: ../` (repo root) and `dockerfile: ../packages/<pkg>/<pkg>.Dockerfile` so package Dockerfiles can `COPY packages/<pkg>` paths.
- Building from inside a package directory is supported by using the helper `build.sh` or by explicitly passing the repo root as the build context (for example: `docker build -f observability.Dockerfile ..`).
