FROM python:3.10-slim

WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy etl_core
COPY packages/etl_core /app/packages/etl_core

# Copy observability
COPY packages/observability /app/packages/observability

# Install dependencies
WORKDIR /app/packages/observability
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

# Entrypoint: expose observability CLI
ENTRYPOINT ["etl-observe"]
CMD ["--help"]
