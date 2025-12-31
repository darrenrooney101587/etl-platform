FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install poetry

# Copy etl_core
COPY packages/etl_core /app/packages/etl_core

# Copy data_pipeline
COPY packages/data_pipeline /app/packages/data_pipeline

# Install dependencies
WORKDIR /app/packages/data_pipeline
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --extras db

# Entrypoint
CMD ["data-pipeline-get-s3-files", "--help"]
