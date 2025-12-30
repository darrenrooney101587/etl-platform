FROM python:3.10-slim

WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy etl_core
COPY packages/etl_core /app/packages/etl_core

# Copy data_pipeline
COPY packages/data_pipeline /app/packages/data_pipeline

# Install dependencies
WORKDIR /app/packages/data_pipeline
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

# Placeholder entrypoint
CMD ["echo", "Data Pipeline Module Started"]
