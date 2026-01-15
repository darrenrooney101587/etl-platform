FROM python:3.10-slim

# Install minimal system build deps for psycopg2
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev ca-certificates && rm -rf /var/lib/apt/lists/*

# Copy code into image
COPY packages/etl_core /app/packages/etl_core
COPY packages/file_processing /app/packages/file_processing
COPY .local/etl-database-schema /app/vendor/etl-database-schema

# Install only runtime Python dependencies via pip to avoid Poetry/build issues
RUN pip install poetry \
    && poetry self add poetry-plugin-export

# Install schema from staged local copy
RUN if [ -d "/app/vendor/etl-database-schema" ] && [ -f "/app/vendor/etl-database-schema/pyproject.toml" ]; then \
      pip install --no-cache-dir /app/vendor/etl-database-schema; \
    else \
      echo "Missing staged schema at /app/vendor/etl-database-schema. Run: ./packages/file_processing/scripts/build.sh"; \
      exit 1; \
    fi

# Install third-party deps (exclude local path deps like etl-core)
WORKDIR /app/packages/file_processing
RUN poetry export -f requirements.txt --without-hashes --output /tmp/requirements_raw.txt \
    && grep -vE '^(etl-core)' /tmp/requirements_raw.txt > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt

# Default workdir for running the package
WORKDIR /app

# Ensure the package parent directory is on PYTHONPATH so 'file_processing' and 'etl_core' import correctly
ENV PYTHONPATH=/app/packages

# Use python -m invocation; set PYTHONPATH at runtime to include mounted package sources
ENTRYPOINT ["python", "-m", "file_processing.cli.main"]
CMD ["--help"]
