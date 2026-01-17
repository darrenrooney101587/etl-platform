# PDF Report Generation and Email Notification

This document describes the PDF report generation and email notification features added to the data quality pipeline.

## Overview

After the data quality and profiling process completes successfully, the system can:
1. Generate a PDF report using a headless browser (Playwright/Chromium)
2. Email the PDF report to configured recipients using SendGrid SMTP

## Components

### 1. PDF Generator (`processors/pdf_generator.py`)

The `PDFGenerator` uses Playwright to render a frontend page as PDF with 100% visual fidelity.

**Features:**
- Headless Chromium browser rendering
- Configurable URL and timeout
- Query parameter support for dynamic reports
- A4 format with margins
- Automatic output directory creation

**Configuration:**
```python
from file_processing.processors.pdf_generator import PDFGenerator, PDFGeneratorConfig

config = PDFGeneratorConfig(
    url="http://localhost:3000/data-quality-report",  # Frontend URL
    timeout_ms=30000,  # Page load timeout
    output_dir="/tmp/pdf_reports"  # Output directory
)

generator = PDFGenerator(config=config)
pdf_path = generator.generate_pdf(
    output_filename="report.pdf",
    query_params={"run_id": "123", "timestamp": "456"}
)
```

### 2. Email Sender (`processors/email_sender.py`)

The `EmailSender` sends emails with PDF attachments via SendGrid SMTP.

**Features:**
- SMTP with TLS encryption
- Multiple recipients support
- HTML and plain text email bodies
- PDF attachment support
- Default recipient configuration

**Configuration:**
```python
from file_processing.processors.email_sender import EmailSender, EmailSenderConfig

config = EmailSenderConfig(
    smtp_host="smtp.sendgrid.net",
    smtp_port=587,
    smtp_user="apikey",
    smtp_password="your-sendgrid-api-key",
    from_address="noreply@etl-platform.example.com",
    from_name="ETL Platform Data Quality",
    default_recipient="admin@example.com"
)

sender = EmailSender(config=config)
sender.send_email(
    to_addresses=["user@example.com"],
    subject="Data Quality Report",
    body_text="Please find attached the data quality report.",
    attachment_paths=["/path/to/report.pdf"]
)
```

### 3. Integrated Job (`jobs/s3_data_quality_with_pdf_email_job.py`)

This job extends the standard `s3_data_quality_job` to include PDF generation and email sending.

**Usage:**
```bash
file-processing s3_data_quality_with_pdf_email_job \
    --event-json '{"bucket": "my-bucket", "key": "path/to/file.csv"}' \
    --email-recipients "user1@example.com,user2@example.com"
```

**Options:**
- `--event-json`: S3 event JSON string
- `--event-file`: Path to file containing S3 event JSON
- `--dry-run`: Run without persisting to database
- `--skip-pdf`: Skip PDF generation and email sending
- `--email-recipients`: Comma-separated list of recipients (overrides default)
- `--trace-id`: Optional trace ID for logging

## Environment Configuration

Add these variables to your `.env` file:

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

## Installation

### Prerequisites

1. Install Python dependencies:
```bash
cd packages/file_processing
poetry install
```

2. Install Playwright browsers:
```bash
playwright install chromium
```

### SendGrid Setup

1. Create a SendGrid account at https://sendgrid.com
2. Generate an API key from Settings > API Keys
3. Set the `SENDGRID_API_KEY` environment variable

## Architecture

### Workflow

1. S3 event triggers data quality job
2. Data quality processor validates and profiles the data
3. If successful, PDF generator renders frontend page
4. Email sender delivers PDF to configured recipients

### Isolation

- PDF generation and email sending are optional (use `--skip-pdf` flag)
- Failures in PDF/email do not fail the data quality job
- All components use dependency injection for testability

## Testing

Run unit tests:
```bash
cd packages/file_processing
PYTHONPATH=../.. python -m pytest tests/unit/test_pdf_generator.py -v
PYTHONPATH=../.. python -m pytest tests/unit/test_email_sender.py -v
```

## Integration with Airflow

The integrated job can be called from Airflow using `KubernetesPodOperator`:

```python
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator

pdf_email_task = KubernetesPodOperator(
    task_id="data_quality_with_pdf",
    name="data-quality-pdf-email",
    image="your-ecr/file-processing:latest",
    cmds=["file-processing"],
    arguments=[
        "s3_data_quality_with_pdf_email_job",
        "--event-json", '{"bucket": "my-bucket", "key": "path/to/file.csv"}',
        "--email-recipients", "team@example.com"
    ],
    env_vars={
        "SENDGRID_API_KEY": "{{ var.value.sendgrid_api_key }}",
        "PDF_REPORT_URL": "{{ var.value.pdf_report_url }}",
    }
)
```

## Troubleshooting

### Playwright Issues

If you get "Executable doesn't exist" error:
```bash
playwright install chromium
```

### SendGrid Connection Issues

- Verify API key is correct
- Check SMTP port (587 for TLS, 465 for SSL)
- Ensure firewall allows outbound SMTP connections

### PDF Generation Timeout

- Increase `PDF_REPORT_TIMEOUT_MS` for slow-loading pages
- Check frontend URL is accessible from the job environment
- Verify network connectivity

## Security Considerations

- Store API keys in environment variables or secrets manager
- Use TLS for SMTP connections
- Restrict PDF report URL to internal networks
- Validate email recipients to prevent spam

## Future Enhancements

- Support for alternative PDF engines (Selenium, wkhtmltopdf)
- Email templating system
- Retry logic for transient failures
- S3 storage for generated PDFs
- Email delivery status tracking
