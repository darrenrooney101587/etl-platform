FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential gcc git curl \
    && rm -rf /var/lib/apt/lists/*

COPY packages/etl_core /app/packages/etl_core
COPY packages/orchestration /app/packages/orchestration

RUN python -m pip install --upgrade pip setuptools wheel
RUN pip install /app/packages/etl_core
RUN pip install /app/packages/orchestration

CMD ["python", "-m", "orchestration.cli.main", "--help"]
