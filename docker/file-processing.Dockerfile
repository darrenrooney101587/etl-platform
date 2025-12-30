FROM python:3.10-slim
CMD ["echo", "File Processing Module Started"]
# Placeholder entrypoint

    && poetry install --no-interaction --no-ansi
RUN poetry config virtualenvs.create false \
WORKDIR /app/packages/file_processing
# Install dependencies

COPY packages/file_processing /app/packages/file_processing
# Copy file_processing

COPY packages/etl_core /app/packages/etl_core
# Copy etl_core

RUN pip install poetry
# Install poetry

WORKDIR /app
