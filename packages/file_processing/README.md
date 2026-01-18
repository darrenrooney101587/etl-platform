# file_processing

This package contains the file processing components for the ETL platform: the SNS listener, the S3 data quality job, processors, repositories, and tests.

## Features

- **Data Quality Validation**: Validates S3 files against schemas with completeness, uniqueness, bounds, and format checks
- **Data Profiling**: Generates statistical summaries and distributions for data analysis
- **PDF Report Generation**: Renders data quality reports as PDF using headless browser (Playwright)
- **Email Notifications**: Sends PDF reports via email using SendGrid SMTP
- **SNS Integration**: HTTP listener for AWS SNS notifications

## PDF Report Generation and Email Notifications

The package includes optional PDF generation and email notification capabilities. After successful data quality validation, the system can:

1. Generate a PDF report using headless Chromium (via Playwright)
2. Send the PDF report to configured recipients via SendGrid SMTP

### Components

- **PDFGenerator** (`processors/pdf_generator.py`): Uses Playwright to render frontend pages as PDF with 100% visual fidelity
- **EmailSender** (`processors/email_sender.py`): Sends emails with PDF attachments via SendGrid SMTP

### Configuration

Add these environment variables to your `.env` file:

```bash
# SendGrid / Email Configuration
SENDGRID_API_KEY=your-sendgrid-api-key
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
DEFAULT_EMAIL_RECIPIENT=admin@example.com
EMAIL_FROM_ADDRESS=noreply@etl-platform.example.com
EMAIL_FROM_NAME=ETL Platform Data Quality

# PDF Report Configuration
PDF_REPORT_URL=http://localhost:3000/data-quality-report
PDF_REPORT_TIMEOUT_MS=30000
```

### Installation

Install with PDF/email extras:

```bash
cd packages/file_processing
poetry install --extras pdf-email
playwright install chromium
```

### Usage

Use the `s3_data_quality_with_pdf_email_job` job to enable PDF and email features:

```bash
file-processing s3_data_quality_with_pdf_email_job \
    --event-json '{"bucket": "my-bucket", "key": "path/to/file.csv"}' \
    --email-recipients "user1@example.com,user2@example.com"
```

Options:
- `--skip-pdf`: Skip PDF generation and email sending
- `--email-recipients`: Comma-separated list of recipients (overrides default)

PDF/email failures do not fail the data quality job; they are logged and the job continues.

## SNS listener runtime behavior

The SNS HTTP listener (`packages/file_processing/cli/sns_main.py`) implements a small in-process HTTP server that accepts AWS SNS HTTP POST requests and forwards the inner S3 event message to the data quality job.

Key behaviors:

- Concurrency control: the server uses a bounded `ThreadPoolExecutor` to limit the number of concurrent job executions in a single pod. Configure with the environment variable `SNS_WORKER_MAX` (default: `10`).

- Circuit breaker: to avoid repeated failing work consuming resources and spamming logs, the server includes a per-pod `CircuitBreaker`.
  - Env vars:
    - `CIRCUIT_BREAKER_MAX_FAILURES` (default `5`) — consecutive failing jobs before the breaker activates.
    - `CIRCUIT_BREAKER_COOLDOWN_SECONDS` (default `60`) — how long to wait before the breaker auto-resets.
  - While active the handler will skip submitting new jobs and respond with `{"status": "skipped"}`. You can change this behavior to return a 5xx if you prefer SNS to retry automatically.
  - The circuit breaker is per-pod (in-memory). Restarting the pod will reset the breaker.

## Jobs

This package contains the following jobs. See their individual reference docs in `jobs_docs/` for detailed runtime information:

- **sns_listener** ([reference](jobs_docs/README_sns_listener.md)): In-process HTTP server that listens for SNS notifications and triggers the data quality job.
- **s3_data_quality_job** ([reference](jobs_docs/README_s3_data_quality_job.md)): Processes a single S3 file to validate data quality.
- **s3_data_quality_with_pdf_email_job**: Extended version of s3_data_quality_job that generates PDF reports and sends emails after successful validation.
- **hello_world** ([reference](jobs_docs/README_hello_world.md)): Simple smoke test job.

## Testing

This package uses `unittest.TestCase` for unit tests.

Run the package tests with:

```bash
python -m unittest discover packages/file_processing/tests -v
```

We include tests that cover the `CircuitBreaker` behavior and the S3 `NoSuchKey` handling in the processor.

## Local Docker development (recommended)

`file_processing` imports ORM models from `etl_database_schema`. To avoid pulling the schema package from GitLab/VPN during each Docker build, we use a sibling checkout staged into the Docker build context.

1) One-time: clone the schema repo next to this repo:
```bash
git clone git@gitlab.dev-benchmarkanalytics.com:etl/etl-database-schema.git ../etl-database-schema
```

2) Ensure you have a local env file:
```bash
cp packages/file_processing/.env.example packages/file_processing/.env
```

3) Build the local image (stages schema into `.local/etl-database-schema` and builds from repo root):
```bash
./packages/file_processing/scripts/build.sh
```

When `etl-database-schema` changes, run `git pull` in `../etl-database-schema` and rebuild:
```bash
cd ../etl-database-schema && git pull
cd -
./packages/file_processing/scripts/build.sh
```
