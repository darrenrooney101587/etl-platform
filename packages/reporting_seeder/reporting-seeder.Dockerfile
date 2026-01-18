# syntax=docker/dockerfile:1.7
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install poetry \
    && poetry self add poetry-plugin-export

COPY packages/etl_core /app/packages/etl_core
COPY packages/reporting_seeder /app/packages/reporting_seeder

ENV PYTHONPATH=/app/packages

WORKDIR /app/packages/reporting_seeder

# Install reporting_seeder third-party deps without installing local path deps (etl-core).
RUN poetry export -f requirements.txt --without-hashes \
    | grep -vE '^etl-core' \
    > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt

ENTRYPOINT ["python", "-m", "reporting_seeder.cli.main"]
CMD ["--help"]
