# file_processing

Combined fileops + data quality runtime lane.
Heavy S3 IO + local scratch workloads.

## Responsibilities

- File unzip / decrypt / materialization
- Quarantine & routing
- Whole‑file quality analysis
- Emit quality artifacts & metrics

## CLI

- `file-processing data-quality --agency-id <id>`: run attachment data quality checks for an agency.
