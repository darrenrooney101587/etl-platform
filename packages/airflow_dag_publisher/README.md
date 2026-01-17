# Airflow DAG Publisher

A CLI tool for generating and publishing Airflow DAG files to S3, enabling independent package deployments.

## Overview

This package provides utilities for:

1. **Generating DAGs**: Create Airflow DAG files from Jinja2 templates
2. **Validating DAGs**: Check DAG syntax and naming conventions
3. **Publishing to S3**: Upload DAGs with safety guardrails
4. **Listing DAGs**: View published DAGs per package

## Installation

```bash
cd packages/airflow_dag_publisher
poetry install
```

## Usage

### Generate a DAG

Create a DAG file using the KubernetesPodOperator template:

```bash
airflow-dag-publisher generate \
  --package-name data_pipeline \
  --dag-id data_pipeline_example_job \
  --job-name example_job \
  --image-tag 270022076279.dkr.ecr.us-gov-west-1.amazonaws.com/data-pipeline:v1.0.0 \
  --output /tmp/data_pipeline_example_job.py \
  --description "Run example_job from data_pipeline" \
  --schedule "@daily" \
  --namespace etl-jobs
```

#### Common Options

- `--schedule`: Cron expression or preset (`@daily`, `@hourly`, `@weekly`, etc.)
- `--retries`: Number of retries on failure (default: 2)
- `--retry-delay`: Minutes between retries (default: 5)
- `--timeout`: Execution timeout in minutes (default: 60)
- `--cpu-request`: CPU resource request (default: 500m)
- `--cpu-limit`: CPU resource limit (default: 1000m)
- `--memory-request`: Memory resource request (default: 512Mi)
- `--memory-limit`: Memory resource limit (default: 1Gi)
- `--env-vars`: Environment variables as `KEY=VALUE` pairs
- `--job-args`: Additional CLI arguments for the job

#### Example with Advanced Options

```bash
airflow-dag-publisher generate \
  --package-name reporting_seeder \
  --dag-id reporting_seeder_refresh_all \
  --job-name refresh_all \
  --image-tag 270022076279.dkr.ecr.us-gov-west-1.amazonaws.com/reporting-seeder:v2.1.0 \
  --output /tmp/reporting_seeder_refresh_all.py \
  --schedule "0 2 * * *" \
  --retries 1 \
  --timeout 120 \
  --cpu-request 1000m \
  --cpu-limit 2000m \
  --memory-request 2Gi \
  --memory-limit 4Gi \
  --env-vars ENVIRONMENT=prod DJANGO_SETTINGS_MODULE=reporting_seeder.settings \
  --job-args --parallel --workers 4 \
  --email-on-failure
```

### Validate a DAG

Check DAG syntax and conventions:

```bash
airflow-dag-publisher validate \
  --package-name data_pipeline \
  --dag-file packages/data_pipeline/airflow_dags/data_pipeline_example_job.py
```

Validation checks:

- Python syntax
- Airflow imports present
- DAG ID follows convention (`<package>_<name>`)
- No spaces or invalid characters in DAG ID

### Publish DAGs to S3

Upload DAG files to S3 for Airflow discovery:

```bash
airflow-dag-publisher publish \
  --bucket etl-airflow-dags-dev \
  --environment dev \
  --package-name data_pipeline \
  --dag-path packages/data_pipeline/airflow_dags
```

#### Publish a Single File

```bash
airflow-dag-publisher publish \
  --bucket etl-airflow-dags-dev \
  --environment dev \
  --package-name data_pipeline \
  --dag-path packages/data_pipeline/airflow_dags/data_pipeline_example_job.py
```

#### Skip Validation

```bash
airflow-dag-publisher publish \
  --bucket etl-airflow-dags-dev \
  --environment dev \
  --package-name data_pipeline \
  --dag-path packages/data_pipeline/airflow_dags \
  --no-validate
```

### List Published DAGs

View DAGs published by a package:

```bash
airflow-dag-publisher list \
  --bucket etl-airflow-dags-dev \
  --environment dev \
  --package-name data_pipeline
```

## DAG Naming Convention

DAG IDs **must** follow this pattern:

```
<package_name>_<dag_name>
```

Examples:

- ✅ `data_pipeline_example_job`
- ✅ `reporting_seeder_refresh_all`
- ✅ `observability_s3_metrics`
- ❌ `example_job` (missing package prefix)
- ❌ `data pipeline example` (spaces not allowed)

This ensures global uniqueness across all packages.

## S3 Layout

Published DAGs are stored in S3 with this structure:

```
s3://<bucket>/<environment>/
└── <package_name>/
    ├── dags/
    │   ├── <dag_id_1>.py
    │   ├── <dag_id_2>.py
    │   └── ...
    └── metadata.json (optional)
```

Example:

```
s3://etl-airflow-dags-dev/dev/
├── data_pipeline/
│   └── dags/
│       ├── data_pipeline_example_job.py
│       └── data_pipeline_agency_data.py
└── reporting_seeder/
    └── dags/
        ├── reporting_seeder_refresh_all.py
        └── reporting_seeder_refresh_agency.py
```

## Safety Guardrails

The publisher enforces several safety checks:

1. **Package prefix isolation**: Each package can only write to `<env>/<package>/`
2. **Environment validation**: Only `dev`, `staging`, `prod` allowed
3. **Bucket existence check**: Verifies S3 bucket is accessible
4. **Pre-publish validation**: Checks DAG syntax before upload
5. **Atomic uploads**: S3 `put-object` is atomic (no partial writes)

## Integration with CI/CD

Use in GitLab CI:

```yaml
publish_dags:
  stage: deploy
  image: python:3.10-slim
  before_script:
    - pip install poetry
    - cd packages/airflow_dag_publisher
    - poetry install
    - cd ../..
  script:
    - |
      poetry run airflow-dag-publisher publish \
        --bucket "${DAG_BUCKET}" \
        --environment "${ENVIRONMENT}" \
        --package-name "${PACKAGE_NAME}" \
        --dag-path "packages/${PACKAGE_NAME}/airflow_dags"
  only:
    - main
```

## Environment Variables

The publisher respects standard AWS environment variables:

- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key
- `AWS_SESSION_TOKEN`: Session token (if using temporary credentials)
- `AWS_REGION`: AWS region (default: `us-gov-west-1`)

## Troubleshooting

### "Bucket does not exist"

Ensure the S3 bucket exists and you have read permissions:

```bash
aws s3 ls s3://<bucket>/
```

### "Failed to publish DAGs: Access Denied"

Check IAM permissions. You need:

```json
{
  "Effect": "Allow",
  "Action": [
    "s3:PutObject",
    "s3:DeleteObject"
  ],
  "Resource": "arn:aws:s3:::<bucket>/<env>/<package>/*"
}
```

### "DAG validation failed: Syntax error"

Fix Python syntax errors in your DAG file. Run locally:

```bash
python <dag_file>.py
```

### "DAG ID does not start with package name"

Rename your DAG ID to follow the convention:

```python
dag_id="<package_name>_<dag_name>"
```

## Development

### Run Tests

```bash
cd packages/airflow_dag_publisher
poetry run pytest
```

### Type Checking

```bash
poetry run mypy airflow_dag_publisher
```

### Code Formatting

```bash
poetry run black airflow_dag_publisher
```

## Architecture

See the main documentation for architecture details:

- [Architecture Overview](../../docs/airflow/README.md)
- [Deployment Guide](../../docs/airflow/DEPLOYMENT.md)
- [Operations Guide](../../docs/airflow/OPERATIONS.md)
