# Airflow Control Plane Infrastructure

This directory contains infrastructure-as-code for deploying the Airflow control plane to Kubernetes.

## Deprecation Notice

The canonical Airflow control plane uses S3-based DAG distribution (see `docs/airflow/README.md` and `infra/airflow/`). This directory is retained for reference but should not be used for new deployments.

## Overview

The Airflow control plane provides automatic DAG generation and synchronization for all ETL jobs in the platform. It consists of:

- **Airflow Scheduler**: Schedules and runs DAGs
- **Airflow Webserver**: Provides the Airflow UI for monitoring and triggering jobs
- **DAG Sync Sidecar**: Periodically discovers jobs and regenerates DAG files
- **Init Container**: Ensures DAGs are synced before Airflow components start

## Architecture

### Components

1. **Init Container** (dag-sync)
   - Runs before Airflow scheduler/webserver starts
   - Discovers all jobs across packages
   - Generates initial DAG files
   - Ensures Airflow has DAGs before starting

2. **DAG Sync Sidecar**
   - Runs alongside the scheduler
   - Periodically syncs DAGs (every 5 minutes by default)
   - Automatically picks up new jobs without manual intervention

3. **Shared Volume**
   - EmptyDir volume shared between containers
   - Contains generated DAG files
   - Mounted at `/opt/airflow/dags`

### How It Works

```
┌─────────────────────────────────────────────────────┐
│  Developer adds new job to any package              │
│  (e.g., packages/data_pipeline/jobs/new_job.py)     │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  Code is deployed (git push, CI/CD, etc.)           │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  DAG Sync Sidecar runs (every 5 min)                │
│  - Scans all packages for JOB tuples                │
│  - Generates DAG files in /opt/airflow/dags         │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  Airflow Scheduler detects new DAGs                 │
│  - DAGs appear in Airflow UI automatically          │
│  - No manual DAG creation required                  │
└─────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Kubernetes cluster (EKS, GKE, or local)
- kubectl configured
- Docker for building images
- Terraform (optional, for AWS resources)

### 1. Build and Push Image

```bash
cd infra/airflow_control_plane
./scripts/ecr_put.sh
```

This builds the control plane image and pushes it to your container registry.

### 2. Create Namespace

```bash
kubectl create namespace airflow
```

### 3. Deploy ConfigMap and Secrets

```bash
kubectl apply -f k8s/airflow-configmap.yaml
kubectl apply -f k8s/airflow-secret.yaml
```

**Important**: Update `airflow-secret.yaml` with:
- A secure Fernet key (generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- Your database connection string

### 4. Deploy Airflow Components

```bash
# Deploy scheduler (includes DAG sync sidecar)
kubectl apply -f k8s/airflow-scheduler-deployment.yaml

# Deploy webserver
kubectl apply -f k8s/airflow-webserver-deployment.yaml
```

### 5. Access Airflow UI

```bash
# Get the webserver service external IP
kubectl get svc -n airflow airflow-webserver

# Or use port-forward for local access
kubectl port-forward -n airflow svc/airflow-webserver 8080:80
```

Access at http://localhost:8080

Default credentials:
- Username: `admin`
- Password: `admin` (change in production)

## Configuration

### Environment Variables

Set in `k8s/airflow-configmap.yaml`:

- `ETL_PACKAGES_ROOT`: Path to packages directory (default: `/app/packages`)
- `AIRFLOW_DAGS_DIR`: DAG output directory (default: `/opt/airflow/dags`)
- `AIRFLOW__CORE__EXECUTOR`: Airflow executor type (default: `LocalExecutor`)

### DAG Sync Interval

The sidecar syncs every 5 minutes by default. To change:

Edit `k8s/airflow-scheduler-deployment.yaml`:

```yaml
args:
  - |
    while true; do
      airflow-control-plane sync
      sleep 600  # Changed to 10 minutes
    done
```

## Deployment Patterns

### Pattern 1: Init Container Only (Restart on Changes)

For environments where you can restart pods when code changes:

```yaml
initContainers:
  - name: dag-sync
    image: etl-airflow-control-plane:latest
    command: ["airflow-control-plane", "sync"]
```

Redeploy when jobs change:
```bash
kubectl rollout restart deployment/airflow-scheduler -n airflow
```

### Pattern 2: Sidecar (Auto-Sync)

For production with frequent changes (current default):

```yaml
containers:
  - name: dag-sync-sidecar
    image: etl-airflow-control-plane:latest
    command: ["/bin/sh", "-c"]
    args:
      - |
        while true; do
          airflow-control-plane sync
          sleep 300
        done
```

No manual intervention required - new jobs appear automatically.

### Pattern 3: CronJob (Scheduled Sync)

For minimal resource usage:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: dag-sync
spec:
  schedule: "*/5 * * * *"  # Every 5 minutes
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: dag-sync
            image: etl-airflow-control-plane:latest
            command: ["airflow-control-plane", "sync"]
```

## Troubleshooting

### DAGs Not Appearing

1. Check if jobs are discovered:
   ```bash
   kubectl exec -n airflow deployment/airflow-scheduler -c dag-sync-sidecar -- \
     airflow-control-plane discover
   ```

2. Check DAG files exist:
   ```bash
   kubectl exec -n airflow deployment/airflow-scheduler -c airflow-scheduler -- \
     ls -la /opt/airflow/dags/
   ```

3. Check Airflow logs:
   ```bash
   kubectl logs -n airflow deployment/airflow-scheduler -c airflow-scheduler
   ```

### DAG Import Errors

Check for Python import errors in Airflow:

```bash
kubectl exec -n airflow deployment/airflow-scheduler -c airflow-scheduler -- \
  airflow dags list-import-errors
```

Common issues:
- Missing `ETL_PACKAGES_ROOT` in environment
- Packages not included in Docker image
- Missing dependencies

### Sidecar Not Syncing

Check sidecar logs:
```bash
kubectl logs -n airflow deployment/airflow-scheduler -c dag-sync-sidecar -f
```

Verify it's running:
```bash
kubectl get pods -n airflow -o jsonpath='{.items[*].spec.containers[*].name}'
```

## Production Considerations

### Database

The provided manifests use a placeholder database connection. For production:

1. Deploy PostgreSQL:
   ```bash
   # Using Terraform
   cd infra/airflow_control_plane/terraform
   terraform apply
   ```

2. Update `airflow-secret.yaml` with production database URL

### Scaling

**Scheduler**: Keep at 1 replica (Airflow limitation)

**Webserver**: Can scale horizontally:
```bash
kubectl scale deployment airflow-webserver -n airflow --replicas=3
```

**Workers**: If using CeleryExecutor, deploy worker pods:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: airflow-worker
spec:
  replicas: 5
  # ... worker configuration
```

### Security

1. **Change default credentials**:
   ```bash
   kubectl exec -n airflow deployment/airflow-scheduler -c airflow-scheduler -- \
     airflow users create \
     --username admin \
     --password <secure-password> \
     --firstname Admin \
     --lastname User \
     --role Admin \
     --email admin@example.com
   ```

2. **Use secrets management**:
   - AWS Secrets Manager
   - HashiCorp Vault
   - Kubernetes External Secrets

3. **Network policies**:
   - Restrict access to Airflow webserver
   - Use Ingress with TLS
   - Enable authentication (LDAP, OAuth, etc.)

### Monitoring

Add Prometheus metrics:
```yaml
env:
  - name: AIRFLOW__METRICS__STATSD_ON
    value: "True"
  - name: AIRFLOW__METRICS__STATSD_HOST
    value: "statsd-exporter"
```

### High Availability

For HA deployment:
- Use PostgreSQL with replication
- Deploy multiple webserver replicas
- Use Redis for Celery (if using CeleryExecutor)
- Set up health checks and liveness probes

## Terraform (AWS Resources)

The `terraform/` directory contains infrastructure for:
- EKS cluster (optional)
- RDS PostgreSQL for Airflow metadata
- S3 bucket for logs
- IAM roles and policies

### Deploy with Terraform

```bash
cd infra/airflow_control_plane
./scripts/manage.sh init
./scripts/manage.sh apply
```

### Update Image

```bash
./scripts/manage.sh update-image
```

## Local Development

### Using Minikube/Kind

```bash
# Start local cluster
minikube start

# Build image locally
eval $(minikube docker-env)
docker build -f packages/airflow_control_plane/airflow-control-plane.Dockerfile \
  -t etl-airflow-control-plane:latest .

# Deploy
kubectl apply -f infra/airflow_control_plane/k8s/
```

### Testing DAG Generation

```bash
# Run sync manually
kubectl exec -n airflow deployment/airflow-scheduler -c dag-sync-sidecar -- \
  airflow-control-plane sync -v

# Check generated DAGs
kubectl exec -n airflow deployment/airflow-scheduler -c airflow-scheduler -- \
  ls -la /opt/airflow/dags/
```

## Scripts Reference

- `scripts/manage.sh` - Terraform lifecycle management
- `scripts/ecr_put.sh` - Build and push Docker image
- `scripts/setup_localstack.sh` - Local development setup

## Related Documentation

- [Airflow Control Plane Package README](../../packages/airflow_control_plane/README.md)
- [Adding New Jobs](../../packages/airflow_control_plane/README.md#developer-workflow)
- [Job Convention](../../packages/etl_core/README.md)
