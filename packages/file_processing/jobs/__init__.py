"""Jobs package for file_processing.

Each job module must export a JOB tuple: (entrypoint, description).
Jobs are discovered automatically by the CLI using etl_core.jobs.discover_package_jobs().

Available jobs:
- s3_data_quality_job: Process S3 objects for data quality validation
"""
