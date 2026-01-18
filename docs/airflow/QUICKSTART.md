# Airflow DAG Quick Start Guide

A quick reference for adding Airflow orchestration to a package.

## Package developers

### 1. Create the DAG directory

```bash
mkdir -p packages/<your_package>/airflow_dags
```

### 2. Write the DAG

Create `packages/<your_package>/airflow_dags/<your_package>_<job_name>.py`:

```text
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
    schedule_interval="@daily",  # or cron: "0 2 * * *"
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["<your_package>"],
) as dag:

    run_job = KubernetesPodOperator(
        task_id="run_<job_name>",
        name="<your-package>-<job-name>",
        namespace="etl-jobs",
        image="${IMAGE_TAG}",  # Replaced by CI
        cmds=["<your_package>"],
        arguments=["run", "<job_name>"],
        env_vars={
            "ENVIRONMENT": "${ENVIRONMENT}",
        },
        container_resources=k8s.V1ResourceRequirements(
            requests={"cpu": "500m", "memory": "512Mi"},
            limits={"cpu": "1000m", "memory": "1Gi"},
        ),
        service_account_name="<your-package>",
        get_logs=True,
        is_delete_operator_pod=True,
        security_context={
            "runAsNonRoot": True,
            "runAsUser": 1000,
            "fsGroup": 1000,
        },
        restart_policy="Never",
    )
```

### 3. Add CI stage

A CI stage that validates and publishes DAGs can be added to package CI. Example inclusion using a shared template:

```yaml
include:
  - local: '.gitlab/ci/dag-publish-template.yml'

stages:
  - test
  - build
  - deploy

publish_dags_dev:
  extends: .dag_publish_template
  variables:
    ENVIRONMENT: dev
    PACKAGE_NAME: <your_package>
    IMAGE_TAG: ${ECR_REPO}/<your_package>:${CI_COMMIT_SHA}
    DAG_BUCKET: ${DAG_BUCKET_DEV}
  dependencies:
    - build_image
  only:
    - main
```

### 4. Configure CI variables

CI/CD variables required for DAG publishing and AWS access:

- `DAG_BUCKET_DEV`: `etl-airflow-dags-dev`
- `AWS_ACCESS_KEY_ID`: (from IAM)
- `AWS_SECRET_ACCESS_KEY`: (from IAM, masked)

### 5. Deploy

Example Git workflow for publishing DAGs from the package repository:

```bash
git add packages/<your_package>/airflow_dags
git commit -m "Add Airflow DAG for <job_name>"
git push origin main
```

Allow 60 seconds for sync and parse; then check the Airflow UI for the DAG.

## Common Patterns

### Daily Schedule at Specific Time

```text
schedule_interval="0 2 * * *"  # 2 AM daily
```

### Multiple Tasks in Sequence

```text
with DAG(...) as dag:
    task1 = KubernetesPodOperator(...)
    task2 = KubernetesPodOperator(...)
    task3 = KubernetesPodOperator(...)
    
    task1 >> task2 >> task3  # Sequential execution
```

### Multiple Tasks in Parallel

```text
with DAG(...) as dag:
    task1 = KubernetesPodOperator(...)
    task2 = KubernetesPodOperator(...)
    task3 = KubernetesPodOperator(...)
    
    [task1, task2] >> task3  # task1 and task2 run in parallel, then task3
```

### Pass Arguments to Job

```text
run_job = KubernetesPodOperator(
    task_id="run_job",
    arguments=["run", "my_job", "--arg1", "value1", "--arg2", "value2"],
    ...
)
```

### Environment Variables

```text
run_job = KubernetesPodOperator(
    task_id="run_job",
    env_vars={
        "ENVIRONMENT": "prod",
        "LOG_LEVEL": "INFO",
        "BATCH_SIZE": "1000",
    },
    ...
)
```

### Resource Limits

```text
# Small job
container_resources=k8s.V1ResourceRequirements(
    requests={"cpu": "250m", "memory": "256Mi"},
    limits={"cpu": "500m", "memory": "512Mi"},
)

# Large job
container_resources=k8s.V1ResourceRequirements(
    requests={"cpu": "2000m", "memory": "4Gi"},
    limits={"cpu": "4000m", "memory": "8Gi"},
)
```

### Email Alerts

```text
default_args = {
    "owner": "my_team",
    "email": ["team@example.com"],
    "email_on_failure": True,
    "email_on_retry": False,
}
```

## Testing Locally

### Generate a DAG

```bash
cd packages/orchestration
poetry install

poetry run airflow-dag-publisher generate \
  --package-name <your_package> \
  --dag-id <your_package>_<job_name> \
  --job-name <job_name> \
  --image-tag <your_image>:latest \
  --output /tmp/test_dag.py
```

### Validate a DAG

```bash
poetry run airflow-dag-publisher validate \
  --package-name <your_package> \
  --dag-file packages/<your_package>/airflow_dags/<dag_file>.py
```

### Publish to Dev (Manual)

```bash
poetry run airflow-dag-publisher publish \
  --bucket etl-airflow-dags-dev \
  --environment dev \
  --package-name <your_package> \
  --dag-path packages/<your_package>/airflow_dags
```

## Troubleshooting

### DAG Not Appearing

1. Allow 60 seconds (sync + parse time)
2. Check CI logs for publish errors
3. Check Airflow scheduler logs: `kubectl logs -n airflow -l component=scheduler`
4. Verify S3: `aws s3 ls s3://etl-airflow-dags-dev/dev/<your_package>/dags/`

### DAG Parse Error

1. Check Airflow UI error message
2. Validate syntax: `python <dag_file>.py`
3. Fix errors and re-publish

### Job Pod Won't Start

1. Inspect pod: `kubectl get pods -n etl-jobs -l dag_id=<dag_id>`
2. Describe pod: `kubectl describe pod -n etl-jobs <pod-name>`
3. Confirm image exists in ECR
4. Verify resource limits are appropriate

## Best Practices

✅ **DO**: Use meaningful DAG IDs: `<package>_<job_name>`  
✅ **DO**: Set appropriate resource limits  
✅ **DO**: Use `catchup=False` for most DAGs  
✅ **DO**: Tag DAGs by package and purpose  
✅ **DO**: Test DAGs in dev before prod  

❌ **DON'T**: Import package code in DAG files  
❌ **DON'T**: Use dynamic DAG generation  
❌ **DON'T**: Set `catchup=True` without good reason  
❌ **DON'T**: Use excessive retries (> 3)  
❌ **DON'T**: Forget to set execution timeout  

## Resources

- [Architecture Overview](README.md)
- [Deployment Guide](DEPLOYMENT.md)
- [Operations Guide](OPERATIONS.md)
- [Implementation Summary](IMPLEMENTATION_SUMMARY.md)
- [DAG Publisher README](../../packages/orchestration/README.md)

## Getting Help

- Check Airflow logs: `kubectl logs -n airflow -l component=scheduler`
- View DAG in Airflow UI: `https://<airflow-url>/dags/<dag_id>`
- Slack: `#etl-platform` channel
- Documentation: `docs/airflow/`
