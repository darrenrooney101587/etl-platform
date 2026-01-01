FROM python:3.10-slim

# Install poetry and set up working dir
WORKDIR /app

RUN pip install poetry

# Copy etl_core and file_processing
COPY packages/etl_core /app/packages/etl_core
COPY packages/file_processing /app/packages/file_processing

# Install dependencies for file_processing
WORKDIR /app/packages/file_processing
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

# Entrypoint: use console script if provided
ENTRYPOINT ["file-processing"]
CMD ["--help"]
