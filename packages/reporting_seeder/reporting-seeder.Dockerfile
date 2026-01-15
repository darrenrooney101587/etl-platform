# syntax=docker/dockerfile:1.7
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install poetry \
    && poetry self add poetry-plugin-export

COPY packages/etl_core /app/packages/etl_core
COPY packages/reporting_seeder /app/packages/reporting_seeder
COPY .local/etl-database-schema /app/vendor/etl-database-schema

ENV PYTHONPATH=/app/packages

WORKDIR /app/packages/reporting_seeder

# Install schema from staged local copy (required for reporting_seeder runtime).
RUN if [ -d "/app/vendor/etl-database-schema" ] && [ -f "/app/vendor/etl-database-schema/pyproject.toml" ]; then \
      pip install --no-cache-dir /app/vendor/etl-database-schema; \
    else \
      echo "Missing staged schema at /app/vendor/etl-database-schema. Run: ./packages/reporting_seeder/scripts/build.sh"; \
      exit 1; \
    fi

# Install reporting_seeder third-party deps without installing local path deps (etl-core).
RUN poetry export -f requirements.txt --without-hashes \
    | grep -vE '^(etl-core|etl-database-schema)' \
    > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt

ENTRYPOINT ["python", "-m", "reporting_seeder.cli.main"]
CMD ["--help"]
