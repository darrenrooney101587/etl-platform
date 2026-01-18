# Airflow Control Plane Infrastructure

This directory contains infrastructure-as-code for deploying the Airflow control plane on EKS.

## Architecture

The Airflow control plane consists of:

- **Scheduler**: Discovers and schedules DAGs from `/opt/airflow/dags`
- **Webserver**: Provides the Airflow UI
- **DAG Sync Sidecar**: Continuously syncs DAGs from S3 to the scheduler's filesystem
- **Metadata Database**: PostgreSQL for Airflow's internal state

## Directory Structure

```
infra/orchestration/
├── terraform/          # S3 bucket, IAM roles, and policies
├── k8s/               # Kubernetes manifests and Helm values
└── scripts/           # Deployment and management scripts
```

## Prerequisites

- EKS cluster with OIDC provider configured
- VPC with private subnets
- kubectl configured to access the cluster
- Helm 3.x installed
- AWS credentials with appropriate permissions

## Deployment

### 1. Deploy Infrastructure (S3 Bucket, IAM)

```bash
cd infra/orchestration/scripts

# Initialize Terraform
./manage.sh init

# Plan changes
ENVIRONMENT=dev \
VPC_ID=vpc-xxx \
SUBNET_IDS=subnet-a,subnet-b \
EKS_CLUSTER_NAME=my-cluster \
./manage.sh plan

# Apply
ENVIRONMENT=dev \
VPC_ID=vpc-xxx \
SUBNET_IDS=subnet-a,subnet-b \
EKS_CLUSTER_NAME=my-cluster \
./manage.sh apply

# Get outputs
./manage.sh outputs
```

### 2. Deploy Airflow to Kubernetes

```bash
# Install Airflow
ENVIRONMENT=dev \
DAG_BUCKET=etl-airflow-dags-dev \
./deploy_airflow.sh install

# Check status
./deploy_airflow.sh status

# View logs
./deploy_airflow.sh logs
```

### 3. Update IRSA Annotation

After Terraform creates the IAM role, update the Helm values:

```yaml
serviceAccount:
  annotations:
    eks.amazonaws.com/role-arn: <airflow_service_account_role_arn from terraform output>
```

Then upgrade the release:

```bash
ENVIRONMENT=dev DAG_BUCKET=etl-airflow-dags-dev ./deploy_airflow.sh upgrade
```

## Local Development

Use kind or minikube with LocalStack for a local control plane and DAG bucket.

### 1. Start a local Kubernetes cluster

```bash
kind create cluster
# or
minikube start
```

### 2. Start LocalStack and create the DAG bucket

```bash
cd infra/orchestration/scripts
ENVIRONMENT=dev ./setup_localstack.sh
```

This provisions `s3://etl-airflow-dags-dev/dev/` in LocalStack.
When running against LocalStack instead of AWS (common for kind/minikube), update the DAG sync sidecar command in `k8s/airflow-values.yaml` to pass `--endpoint-url` for the LocalStack endpoint.
Choose an address reachable from the cluster:
- Docker Desktop: `http://host.docker.internal:4566`
- In-cluster LocalStack service: `http://localstack:4566`
- Docker-based LocalStack on the host: `http://<host-ip>:4566`
Replace the endpoint in the example below with the address that matches your setup.

```yaml
command:
  - /bin/sh
  - -c
  - |
    # ... existing setup ...
    aws s3 sync "${S3_PREFIX}/" "${LOCAL_DAG_DIR}/" \
      --delete --exact-timestamps --no-progress \
      --endpoint-url http://host.docker.internal:4566
    while true; do
      # ... existing loop ...
      aws s3 sync "${S3_PREFIX}/" "${LOCAL_DAG_DIR}/" \
        --delete --exact-timestamps --no-progress \
        --endpoint-url http://host.docker.internal:4566
    done
```

### 3. Deploy Airflow with Helm

```bash
cd infra/orchestration/scripts
ENVIRONMENT=dev DAG_BUCKET=etl-airflow-dags-dev ./deploy_airflow.sh install
```

### 4. Access the Airflow UI

```bash
kubectl port-forward -n airflow svc/airflow-webserver 8080:80
```

Open http://localhost:8080.

## DAG Distribution Flow

1. Package CI generates DAG files
2. Package CI uploads DAGs to `s3://<bucket>/<env>/<package>/dags/`
3. DAG sync sidecar detects changes and syncs to `/opt/airflow/dags`
4. Airflow scheduler discovers new DAGs on its parse cycle (every 30s)

## Configuration

### S3 Bucket Layout

```
s3://etl-airflow-dags-<env>/
└── <env>/
    ├── pipeline_processing/
    │   ├── dags/
    │   │   └── pipeline_processing_example_job.py
    │   └── metadata.json
    └── reporting_seeder/
        ├── dags/
        │   └── reporting_seeder_refresh.py
        └── metadata.json
```

### Airflow Configuration

Key settings in `airflow-values.yaml`:

- `AIRFLOW__CORE__DAGS_FOLDER`: `/opt/airflow/dags`
- `AIRFLOW__SCHEDULER__DAG_DIR_LIST_INTERVAL`: `30` (seconds)
- `AIRFLOW__KUBERNETES__NAMESPACE`: `etl-jobs`

### DAG Sync Sidecar

The sidecar runs `aws s3 sync` every 30 seconds:

```bash
aws s3 sync s3://<bucket>/<env>/ /opt/airflow/dags/ --delete --exact-timestamps
```

## Operations

### View DAG Sync Logs

```bash
kubectl logs -n airflow -l component=scheduler -c dag-sync --tail=100 -f
```

### Manually Trigger Sync

```bash
kubectl exec -n airflow -c dag-sync \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- aws s3 sync s3://<bucket>/<env>/ /opt/airflow/dags/
```

### List DAGs in S3

```bash
aws s3 ls s3://etl-airflow-dags-dev/dev/ --recursive
```

### Verify DAGs in Scheduler

```bash
kubectl exec -n airflow \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- ls -R /opt/airflow/dags/
```

## Troubleshooting

### DAGs Not Appearing

1. Check sidecar logs: `./deploy_airflow.sh logs`
2. Verify S3 bucket exists and has correct permissions
3. Check IRSA role is attached to service account
4. Verify DAG files are valid Python syntax

### Sync Errors

Common issues:
- Missing IAM permissions
- Incorrect bucket name in ConfigMap
- Network connectivity to S3

### Scheduler Not Parsing DAGs

- Check scheduler logs for import errors
- Verify `dag_dir_list_interval` is set correctly
- Ensure DAGs have valid `dag_id` and don't have syntax errors

## Cost Optimization

- DAG bucket has lifecycle rules to expire old versions after 90 days
- Versioning enabled for rollback capability
- Sidecar uses minimal resources (100m CPU, 128Mi memory)

## Security

- DAG bucket blocks all public access
- Airflow uses IRSA for S3 access (no credentials in pods)
- Package CI roles limited to write within their prefix only
- Scheduler has read-only access to DAG bucket
