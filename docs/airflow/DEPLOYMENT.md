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
cd infra/orchestration/scripts
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

Required outputs from the Terraform apply:
- `dag_bucket_name`: S3 bucket for DAGs
- `airflow_service_account_role_arn`: IAM role ARN for Airflow (IRSA)
- `package_dag_write_policy_arn`: IAM policy ARN for package CI

### Step 2: Deploy Airflow to Kubernetes

Update the Helm values with the IAM role ARN by editing `infra/orchestration/k8s/airflow-values.yaml`:

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

Check the sidecar sync logs:

```bash
kubectl logs -n airflow -l component=scheduler -c dag-sync --tail=50 -f
```

Expected output example:

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

Verify scheduler visibility of the DAG directory:

```bash
kubectl exec -n airflow \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- ls -R /opt/airflow/dags/
```

## Package Integration

Package CI must publish DAG artifacts to the shared DAG bucket and follow the DAG authoring contract.

### Step 1: Create DAG Files

DAG files are expected in a package-local `airflow_dags/` directory. Example layout:

```bash
mkdir -p packages/<your_package>/airflow_dags
```

Reference DAG template (KubernetesPodOperator pattern):

```text
# packages/<your_package>/airflow_dags/<your_package>_<job_name>.py
# Example (pseudo-code, import-free):
# dag_id = "<your_package>_<job_name>"
# default_args = {"owner": "<your_package>", "retries": 2}
# tasks:
# - KubernetesPodOperator(
#     task_id="run_<job_name>",
#     namespace="etl-jobs",
#     image="<ECR_REPO>/<your_package>:<IMAGE_TAG>",
#     cmds=["<your_package>"],
#     arguments=["run", "<job_name>"],
# )
# See package examples under packages/<package>/airflow_dags/ for full, runnable DAG files.
```

Existing examples:
- `packages/pipeline_processing/airflow_dags/`
- `packages/reporting_seeder/airflow_dags/`

### Step 2: Add GitLab CI Stage

A CI stage that validates and publishes DAGs can be added to package CI. Two integration options are provided: shared template inclusion or an inline job definition.

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
    - cd packages/orchestration
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

CI/CD variables required for DAG publishing and AWS access:

| Variable | Description | Example |
|----------|-------------|---------|
| `DAG_BUCKET_DEV` | S3 bucket for dev | `etl-airflow-dags-dev` |
| `DAG_BUCKET_STAGING` | S3 bucket for staging | `etl-airflow-dags-staging` |
| `DAG_BUCKET_PROD` | S3 bucket for prod | `etl-airflow-dags-prod` |
| `AWS_ACCESS_KEY_ID` | AWS credentials (masked) | From IAM user/role |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials (masked) | From IAM user/role |
| `AWS_REGION` | AWS region | `us-gov-west-1` |

### Step 4: Attach IAM Policy to CI Role

The package DAG write policy must be attached to the IAM role or user used by CI. Example attachment flow:

```bash
# Get the policy ARN from Terraform outputs
cd infra/orchestration/scripts
POLICY_ARN=$(./manage.sh outputs | grep package_dag_write_policy_arn | awk '{print $3}' | tr -d '"')

# Attach to the CI role
aws iam attach-role-policy \
  --role-name gitlab-ci-runner-role \
  --policy-arn "$POLICY_ARN"
```

## Verification

### Test DAG Publishing Locally

Install the airflow-dag-publisher package:

```bash
cd packages/orchestration
poetry install
```

Validate a DAG file:

```bash
poetry run airflow-dag-publisher validate \
  --package-name <your_package> \
  --dag-file ../packages/<your_package>/airflow_dags/<dag_file>.py
```

Publish to dev (AWS credentials required):

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

- Allow 30-60 seconds for sync and parse
- Open the Airflow UI
- Navigate to the DAGs page and search for the DAG ID: `<your_package>_<job_name>`
- Confirm the DAG appears and is not paused
- Trigger a manual run to test execution

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

- Schedule: manual triggers or infrequent schedules are recommended
- Resources: smaller limits for cost savings
- Retries: more retries for debugging
- Email alerts: disabled or routed to a development alerting channel

### Staging

- Schedule: mirror production schedules
- Resources: match production resources
- Retries: production-like settings
- Email alerts: enabled for critical failures

### Production

- Schedule: business-defined schedules
- Resources: adequate for SLAs
- Retries: conservative (avoid infinite retries)
- Email alerts: enabled with on-call routing
- SLA monitoring: enabled

### Example: Multi-Environment CI Configuration

```yaml
.dag_publish_base:
  extends: .dag_publish_template
  variables:
    PACKAGE_NAME: pipeline_processing

publish_dags_dev:
  extends: .dag_publish_base
  variables:
    ENVIRONMENT: dev
    IMAGE_TAG: ${ECR_REPO}/pipeline-processing:${CI_COMMIT_SHA}
    DAG_BUCKET: ${DAG_BUCKET_DEV}
  only:
    - main

publish_dags_staging:
  extends: .dag_publish_base
  variables:
    ENVIRONMENT: staging
    IMAGE_TAG: ${ECR_REPO}/pipeline-processing:${CI_COMMIT_TAG}
    DAG_BUCKET: ${DAG_BUCKET_STAGING}
  only:
    - tags

publish_dags_prod:
  extends: .dag_publish_base
  variables:
    ENVIRONMENT: prod
    IMAGE_TAG: ${ECR_REPO}/pipeline-processing:${CI_COMMIT_TAG}
    DAG_BUCKET: ${DAG_BUCKET_PROD}
  only:
    - tags
  when: manual
```

## Rollback Procedures

### Rollback a DAG

- Identify the version to rollback to in S3
- Re-upload the old version:

```bash
aws s3 cp \
  s3://<bucket>/<env>/<package>/dags/<dag_file>.py?versionId=<version_id> \
  s3://<bucket>/<env>/<package>/dags/<dag_file>.py
```

- Allow 30-60 seconds for sync
- Confirm the DAG state in Airflow UI

### Delete a DAG

- Remove the DAG file from S3:

```bash
aws s3 rm s3://<bucket>/<env>/<package>/dags/<dag_file>.py
```

- Allow 30-60 seconds for sync
- The DAG will be removed from the Airflow UI

### Emergency: Disable All Package DAGs

Pause all DAGs for a package via Airflow CLI:

```bash
kubectl exec -n airflow \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- airflow dags pause <your_package>_*
```

## Troubleshooting

Refer to [OPERATIONS.md](OPERATIONS.md) for detailed troubleshooting guidance.

## Next Steps

- Configure monitoring and alerting
- Set up SLA tracking for critical DAGs
- Document runbook procedures for the package
- Train team on Airflow UI and operational patterns
