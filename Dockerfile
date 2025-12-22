FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .[dev]

EXPOSE 8000

CMD ["uvicorn", "file_monitoring.api:app", "--host", "0.0.0.0", "--port", "8000"]
