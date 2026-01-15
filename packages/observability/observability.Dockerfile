FROM python:3.10-slim

WORKDIR /app

# Minimal system deps required at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy packages into image (build context is repo root)
COPY packages/etl_core /app/packages/etl_core
COPY packages/observability /app/packages/observability

# Install runtime dependencies
RUN pip install --no-cache-dir django==4.2.27 slack_sdk==3.39.0 psycopg2-binary==2.9.11 python-json-logger==4.0.0

# Ensure package parent directory is on PYTHONPATH
ENV PYTHONPATH=/app/packages

# Entrypoint: job-driven execution via CLI
ENTRYPOINT ["python", "-m", "observability.cli.main"]
