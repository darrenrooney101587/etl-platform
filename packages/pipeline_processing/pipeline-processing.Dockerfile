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

# Copy pipeline_processing
COPY packages/pipeline_processing /app/packages/pipeline_processing

# Install dependencies
WORKDIR /app/packages/pipeline_processing
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

# Entrypoint: expose the installed console script (stable for EKS Jobs)
ENTRYPOINT ["pipeline-processing"]
CMD ["--help"]

