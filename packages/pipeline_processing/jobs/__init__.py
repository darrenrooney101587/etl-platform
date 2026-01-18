"""Jobs package for pipeline_processing.

Each job module must export a JOB tuple: (entrypoint, description).
Jobs are discovered automatically by the CLI using etl_core.jobs.discover_package_jobs().

Available jobs:
- agency_data_job: Process S3 files and employment history for an agency
- example_job: Example job demonstrating the JOB convention
- s3_data_quality_job: Process S3 objects for data quality validation
- s3_data_quality_with_pdf_email_job: Process S3 objects with PDF report generation and email
- sns_listener: SNS listener for file processing events
- hello_world: Simple hello world job
"""
