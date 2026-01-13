FROM python:3.10-slim

# Install minimal system build deps for psycopg2
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev ca-certificates && rm -rf /var/lib/apt/lists/*

# Copy code into image
COPY packages/etl_core /app/packages/etl_core
COPY packages/file_processing /app/packages/file_processing

# Install only runtime Python dependencies via pip to avoid Poetry/build issues
RUN pip install poetry

# Default workdir for running the package
WORKDIR /app

# Ensure the package parent directory is on PYTHONPATH so 'file_processing' and 'etl_core' import correctly
ENV PYTHONPATH=/app/packages

# Use python -m invocation; set PYTHONPATH at runtime to include mounted package sources
ENTRYPOINT ["python", "-m", "file_processing.cli.main"]
CMD ["--help"]
