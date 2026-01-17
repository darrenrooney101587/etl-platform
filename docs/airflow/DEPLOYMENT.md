# Airflow DAG Distribution - Deployment Guide

This document describes how to deploy the Airflow DAG distribution system from infrastructure to CI/CD integration.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Infrastructure Deployment](#infrastructure-deployment)
- [Package Integration](#package-integration)
- [Verification](#verification)
- [Environment-Specific Configuration](#environment-specific-configuration)

## Prerequisites

### Infrastructure

- EKS cluster with OIDC provider configured
- VPC with private subnets
- kubectl configured to access the cluster
- Helm 3.x installed
- Terraform 1.5+

### Permissions

- AWS credentials with permissions to:
  - Create S3 buckets
  - Create IAM roles and policies
  - Deploy to EKS
- GitLab CI/CD variables configured (see below)

## Infrastructure Deployment

### Step 1: Deploy S3 Bucket and IAM (Terraform)

Navigate to the Airflow infrastructure directory:

```bash
cd infra/airflow/scripts
```

Initialize Terraform:

```bash
./manage.sh init
```

Plan and review changes:

```bash
ENVIRONMENT=dev \
VPC_ID=vpc-xxxxxxxxx \
SUBNET_IDS=subnet-aaa,subnet-bbb \
EKS_CLUSTER_NAME=etl-cluster-dev \
./manage.sh plan
```

Apply infrastructure:

```bash
ENVIRONMENT=dev \
VPC_ID=vpc-xxxxxxxxx \
SUBNET_IDS=subnet-aaa,subnet-bbb \
EKS_CLUSTER_NAME=etl-cluster-dev \
./manage.sh apply
```

Capture outputs:

```bash
./manage.sh outputs
```

You'll need these values:
- `dag_bucket_name`: S3 bucket for DAGs
- `airflow_service_account_role_arn`: IAM role ARN for Airflow (IRSA)
- `package_dag_write_policy_arn`: IAM policy ARN for package CI

### Step 2: Deploy Airflow to Kubernetes

Update the Helm values with the IAM role ARN:

Edit `infra/airflow/k8s/airflow-values.yaml`:

```yaml
serviceAccount:
  annotations:
    eks.amazonaws.com/role-arn: <airflow_service_account_role_arn>
```

Install Airflow:

```bash
ENVIRONMENT=dev \
DAG_BUCKET=<dag_bucket_name> \
./deploy_airflow.sh install
```

Check status:

```bash
./deploy_airflow.sh status
```

View logs:

```bash
./deploy_airflow.sh logs
```

### Step 3: Verify DAG Sync

Check that the sidecar is syncing:

```bash
kubectl logs -n airflow -l component=scheduler -c dag-sync --tail=50 -f
```

Expected output:

```
Starting DAG sync sidecar...
Configuration:
  S3 Bucket: etl-airflow-dags-dev
  Environment: dev
  S3 Prefix: s3://etl-airflow-dags-dev/dev
  Local DAG Dir: /opt/airflow/dags
  Sync Interval: 30s
Performing initial sync...
Initial sync complete.
2024-01-17T12:00:00Z - Syncing DAGs from S3...
No changes detected.
```

Verify the scheduler can see the DAG directory:

```bash
kubectl exec -n airflow \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- ls -R /opt/airflow/dags/
```

## Package Integration

Each package needs to integrate DAG publishing into its CI/CD pipeline.

### Step 1: Create DAG Files

Create an `airflow_dags/` directory in your package:

```bash
mkdir -p packages/<your_package>/airflow_dags
```

Add your DAG files following the KubernetesPodOperator pattern:

```python
# packages/<your_package>/airflow_dags/<your_package>_<job_name>.py
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import (
    KubernetesPodOperator,
)
from kubernetes.client import models as k8s

default_args = {
    "owner": "<your_package>",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="<your_package>_<job_name>",
    default_args=default_args,
    description="Run <job_name> from <your_package>",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["<your_package>"],
) as dag:

    run_job = KubernetesPodOperator(
        task_id="run_<job_name>",
        name="<your-package>-<job-name>",
        namespace="etl-jobs",
        image="<ECR_REPO>/<your_package>:latest",  # Updated by CI
        cmds=["<your_package>"],
        arguments=["run", "<job_name>"],
        # ... resource limits, service account, etc.
    )
```

See example DAGs in:
- `packages/data_pipeline/airflow_dags/`
- `packages/reporting_seeder/airflow_dags/`

### Step 2: Add GitLab CI Stage

Update your package's `.gitlab-ci.yml` to include the DAG publishing stage.

Option A: Include the shared template (recommended):

```yaml
include:
  - local: '.gitlab/ci/dag-publish-template.yml'

stages:
  - test
  - build
  - deploy

# ... existing stages ...

publish_dags_dev:
  extends: .dag_publish_template
  variables:
    ENVIRONMENT: dev
    PACKAGE_NAME: <your_package>
    IMAGE_TAG: ${ECR_REPO}/<your_package>:${CI_COMMIT_SHA}
    DAG_BUCKET: ${DAG_BUCKET_DEV}
  dependencies:
    - build_image  # Ensure image is built first
  only:
    - main
```

Option B: Define inline:

```yaml
publish_dags_dev:
  stage: deploy
  image: python:3.10-slim
  before_script:
    - apt-get update && apt-get install -y git
    - pip install poetry
    - cd packages/airflow_dag_publisher
    - poetry config virtualenvs.create false
    - poetry install --no-interaction
    - cd ../..
  script:
    - |
      airflow-dag-publisher publish \
        --bucket "${DAG_BUCKET_DEV}" \
        --environment dev \
        --package-name "<your_package>" \
        --dag-path "packages/<your_package>/airflow_dags"
  only:
    - main
```

### Step 3: Configure CI/CD Variables

Add these variables to your GitLab project (Settings → CI/CD → Variables):

| Variable | Description | Example |
|----------|-------------|---------|
| `DAG_BUCKET_DEV` | S3 bucket for dev | `etl-airflow-dags-dev` |
| `DAG_BUCKET_STAGING` | S3 bucket for staging | `etl-airflow-dags-staging` |
| `DAG_BUCKET_PROD` | S3 bucket for prod | `etl-airflow-dags-prod` |
| `AWS_ACCESS_KEY_ID` | AWS credentials (masked) | From IAM user/role |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials (masked) | From IAM user/role |
| `AWS_REGION` | AWS region | `us-gov-west-1` |

### Step 4: Attach IAM Policy to CI Role

Attach the `package_dag_write_policy` to the IAM role/user used by GitLab CI:

```bash
# Get the policy ARN from Terraform outputs
cd infra/airflow/scripts
POLICY_ARN=$(./manage.sh outputs | grep package_dag_write_policy_arn | awk '{print $3}' | tr -d '"')

# Attach to your CI role
aws iam attach-role-policy \
  --role-name gitlab-ci-runner-role \
  --policy-arn "$POLICY_ARN"
```

## Verification

### Test DAG Publishing Locally

Install the airflow-dag-publisher package:

```bash
cd packages/airflow_dag_publisher
poetry install
```

Validate your DAG:

```bash
poetry run airflow-dag-publisher validate \
  --package-name <your_package> \
  --dag-file ../packages/<your_package>/airflow_dags/<dag_file>.py
```

Publish to dev (requires AWS credentials):

```bash
poetry run airflow-dag-publisher publish \
  --bucket etl-airflow-dags-dev \
  --environment dev \
  --package-name <your_package> \
  --dag-path packages/<your_package>/airflow_dags
```

List published DAGs:

```bash
poetry run airflow-dag-publisher list \
  --bucket etl-airflow-dags-dev \
  --environment dev \
  --package-name <your_package>
```

### Verify DAG in Airflow

1. Wait 30-60 seconds for sync and parse
2. Open the Airflow UI
3. Navigate to the DAGs page
4. Search for your DAG ID: `<your_package>_<job_name>`
5. Verify the DAG appears and is not paused
6. Trigger a manual run to test execution

Check scheduler logs for parse errors:

```bash
kubectl logs -n airflow -l component=scheduler --tail=100 | grep -i error
```

### Verify Job Execution

Trigger the DAG from the UI and monitor:

```bash
# Watch jobs in the etl-jobs namespace
kubectl get pods -n etl-jobs -w

# View job logs
kubectl logs -n etl-jobs <pod-name> -f
```

## Environment-Specific Configuration

### Development

- Schedule: Use manual triggers or infrequent schedules
- Resources: Smaller limits for cost savings
- Retries: More retries for debugging
- Email alerts: Disabled or sent to dev team

### Staging

- Schedule: Mirror production schedules
- Resources: Match production resources
- Retries: Production-like settings
- Email alerts: Enabled for critical failures

### Production

- Schedule: Business-defined schedules
- Resources: Adequate for SLAs
- Retries: Conservative (avoid infinite retries)
- Email alerts: Enabled with on-call routing
- SLA monitoring: Enabled

### Example: Multi-Environment CI Configuration

```yaml
.dag_publish_base:
  extends: .dag_publish_template
  variables:
    PACKAGE_NAME: data_pipeline

publish_dags_dev:
  extends: .dag_publish_base
  variables:
    ENVIRONMENT: dev
    IMAGE_TAG: ${ECR_REPO}/data-pipeline:${CI_COMMIT_SHA}
    DAG_BUCKET: ${DAG_BUCKET_DEV}
  only:
    - main

publish_dags_staging:
  extends: .dag_publish_base
  variables:
    ENVIRONMENT: staging
    IMAGE_TAG: ${ECR_REPO}/data-pipeline:${CI_COMMIT_TAG}
    DAG_BUCKET: ${DAG_BUCKET_STAGING}
  only:
    - tags

publish_dags_prod:
  extends: .dag_publish_base
  variables:
    ENVIRONMENT: prod
    IMAGE_TAG: ${ECR_REPO}/data-pipeline:${CI_COMMIT_TAG}
    DAG_BUCKET: ${DAG_BUCKET_PROD}
  only:
    - tags
  when: manual
```

## Rollback Procedures

### Rollback a DAG

1. Identify the version to rollback to in S3
2. Re-upload the old version:

```bash
aws s3 cp \
  s3://<bucket>/<env>/<package>/dags/<dag_file>.py?versionId=<version_id> \
  s3://<bucket>/<env>/<package>/dags/<dag_file>.py
```

3. Wait for sync (30-60 seconds)
4. Verify in Airflow UI

### Delete a DAG

1. Delete from S3:

```bash
aws s3 rm s3://<bucket>/<env>/<package>/dags/<dag_file>.py
```

2. Wait for sync (30-60 seconds)
3. DAG will be removed from Airflow UI

### Emergency: Disable All Package DAGs

Pause all DAGs for a package via Airflow CLI:

```bash
kubectl exec -n airflow \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- airflow dags pause <your_package>_*
```

## Troubleshooting

See [OPERATIONS.md](OPERATIONS.md) for detailed troubleshooting guidance.

## Next Steps

- Configure monitoring and alerting
- Set up SLA tracking for critical DAGs
- Document runbook procedures for your package
- Train team on Airflow UI and operational patterns
