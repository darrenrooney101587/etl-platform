# s3_data_quality_with_pdf_email_job

This job extends the `s3_data_quality_job` by generating a PDF report and emailing it to recipients after successful validation.

## Components

- `S3DataQualityProcessor` — core validation and profiling logic
- `PDFGenerator` — renders a frontend report to PDF using Playwright/Chromium
- `EmailSender` — sends emails via SMTP (configured for SendGrid in production)

## Environment

Required (examples):

- `SENDGRID_API_KEY` or SMTP credentials
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- `PDF_REPORT_URL` — URL of the locally-hosted report frontend (used by Playwright)

These are typically set in `packages/pipeline_processing/.env` for local development.

## Invocation

```bash
# Docker
docker run --rm etl-pipeline-processing \
  pipeline-processing run s3_data_quality_with_pdf_email_job \
  --event-json '{"Records": [{"s3": {"bucket": {"name": "my-bucket"}, "object": {"key": "my-key"}}}]}' \
  --email-recipients user1@example.com,user2@example.com
```

```bash
# Local (poetry)
cd packages/pipeline_processing
PYTHONPATH=../.. poetry run python -m pipeline_processing.cli.main run s3_data_quality_with_pdf_email_job \
  --event-file ./packages/pipeline_processing/event.json --email-recipients user1@example.com
```

## Flow

1. Run standard data quality checks (parsing, schema validation, profiling).
2. If validation completes and results meet configured thresholds, generate a PDF using the configured `PDF_REPORT_URL` and Playwright.
3. Attach PDF and send email to recipients using SMTP/SendGrid. Email sending failures are logged but do not cause the job to fail (configurable behavior).

## Options

- `--skip-pdf`: Skip PDF generation and email sending (useful for fast validation runs).
- `--email-recipients`: Comma-separated list to override default recipients.
- `--dry-run`: Do not persist job-run metadata.

## Testing

- Unit tests should mock Playwright/Chromium and SMTP sending interfaces.
- Add an integration test that runs PDF generation against a lightweight local frontend (optional).

## Observability

- Emit structured logs containing validation summary (row count, failures).
- Email delivery attempts should be recorded in job metadata for auditing.
