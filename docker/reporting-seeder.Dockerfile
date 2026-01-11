FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install poetry

COPY packages/etl_core /app/packages/etl_core
COPY packages/reporting_seeder /app/packages/reporting_seeder

WORKDIR /app/packages/reporting_seeder
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

ENTRYPOINT ["reporting-seeder"]
CMD ["--help"]
