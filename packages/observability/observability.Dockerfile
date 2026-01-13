FROM python:3.10-slim

WORKDIR /app

# Minimal system deps required at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy packages into image (build context is repo root)
COPY packages/etl_core /app/packages/etl_core
COPY packages/observability /app/packages/observability

# Ensure package parent directory is on PYTHONPATH
ENV PYTHONPATH=/app/packages

# Entrypoint: run the observability CLI module
ENTRYPOINT ["python", "-m", "observability.cli.main"]
CMD ["--help"]
