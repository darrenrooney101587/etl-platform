# Airflow Control Plane

This package provides automatic DAG generation and synchronization for ETL jobs across all packages in the platform.

## Deprecation Notice

The canonical Airflow control plane uses S3-based DAG distribution (see `docs/airflow/README.md`, `infra/airflow/`, and `packages/airflow_dag_publisher/`). This package is retained for reference and should not be used for new workflows.

## Overview

The Airflow control plane solves the problem of keeping Airflow DAGs in sync with ETL jobs. When developers add new jobs to any package (e.g., `data_pipeline`, `file_processing`), the control plane automatically:

1. **Discovers** all jobs that follow the `JOB` tuple convention
2. **Generates** Airflow DAG files for each job
3. **Synchronizes** the Airflow scheduler so new jobs appear automatically

## Key Features

- **Zero Configuration**: Jobs are auto-discovered using the existing `JOB` tuple convention
- **Package Isolation**: Each job runs in isolation with proper dependency injection
- **Manual Triggers**: DAGs are created with manual scheduling by default (no accidental runs)
- **Auto-Sync**: DAGs stay in sync with codebase changes
- **Clean-up**: Removes stale DAG files when jobs are deleted

## How It Works

### Job Discovery

The control plane scans all packages in the `packages/` directory and looks for modules in the `jobs/` subdirectory that export a `JOB` tuple:

```python
# packages/data_pipeline/jobs/example_job.py

def entrypoint(argv: List[str]) -> int:
    # Job implementation
    return 0

JOB = (entrypoint, "Example job description")
```

### DAG Generation

For each discovered job, the control plane generates an Airflow DAG file with:

- **Unique DAG ID**: `{package_name}_{job_name}`
- **Manual Schedule**: `schedule_interval=None` (trigger manually via UI/API)
- **Proper Tags**: Includes package name and 'auto-generated' tag
- **Error Handling**: Proper exception handling and logging
- **Retry Logic**: Configurable retries with exponential backoff

### Example Generated DAG

```python
# dags/data_pipeline_example_job_dag.py (auto-generated)

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

def run_job(**context):
    from data_pipeline.jobs.example_job import JOB
    entrypoint, description = JOB
    exit_code = entrypoint([])
    if exit_code != 0:
        raise RuntimeError(f"Job exited with code {exit_code}")

dag = DAG(
    dag_id='data_pipeline_example_job',
    description='Example job description',
    schedule_interval=None,  # Manual trigger
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['data_pipeline', 'etl', 'auto-generated'],
)

task = PythonOperator(
    task_id='run_example_job',
    python_callable=run_job,
    dag=dag,
)
```

## Usage

### CLI Commands

The control plane provides three main commands:

#### 1. Discover Jobs

List all discoverable jobs across packages:

```bash
airflow-control-plane discover
```

Output:
```
Discovered jobs in 2 package(s):

📦 data_pipeline
  └─ example_job: Example job description
  └─ agency_data_job: Process agency data

📦 file_processing
  └─ hello_world: Hello world smoke-test job
  └─ s3_data_quality_job: Process S3 file for data quality

Total: 4 job(s)
```

#### 2. Generate DAGs

Generate Airflow DAG files:

```bash
airflow-control-plane generate --dags-dir ./dags
```

Options:
- `--packages-root`: Path to packages directory (default: auto-detect)
- `--dags-dir`: Output directory for DAGs (default: `./dags` or `$AIRFLOW_DAGS_DIR`)
- `--clean`: Remove stale DAG files for deleted jobs

#### 3. Sync DAGs

Discover + generate + clean in one command:

```bash
airflow-control-plane sync --dags-dir ./dags
```

This is the recommended command to run as part of your deployment/CI process.

### Environment Variables

- `ETL_PACKAGES_ROOT`: Path to the packages directory (e.g., `/app/packages`)
- `AIRFLOW_DAGS_DIR`: Default output directory for generated DAGs

### Integration with Airflow

#### Option 1: Volume Mount (Development)

Mount the packages directory into the Airflow container:

```yaml
# docker-compose.yml
services:
  airflow-scheduler:
    image: apache/airflow:2.8.0
    volumes:
      - ./packages:/app/packages
      - ./dags:/opt/airflow/dags
    environment:
      - ETL_PACKAGES_ROOT=/app/packages
      - AIRFLOW_DAGS_DIR=/opt/airflow/dags
```

Run sync before starting Airflow:

```bash
airflow-control-plane sync --packages-root ./packages --dags-dir ./dags
docker-compose up airflow-scheduler
```

#### Option 2: Init Container (Kubernetes)

Use an init container to generate DAGs before Airflow starts:

```yaml
# k8s/airflow-deployment.yaml
initContainers:
  - name: dag-sync
    image: etl-airflow-control-plane:latest
    command: ["airflow-control-plane", "sync"]
    env:
      - name: ETL_PACKAGES_ROOT
        value: /app/packages
      - name: AIRFLOW_DAGS_DIR
        value: /opt/airflow/dags
    volumeMounts:
      - name: dags
        mountPath: /opt/airflow/dags
```

#### Option 3: Sidecar (Production)

Run the control plane as a sidecar that periodically syncs DAGs:

```yaml
# k8s/airflow-deployment.yaml
containers:
  - name: airflow-scheduler
    image: apache/airflow:2.8.0
    # ...
  
  - name: dag-sync
    image: etl-airflow-control-plane:latest
    command: ["/bin/sh", "-c"]
    args:
      - |
        while true; do
          airflow-control-plane sync
          sleep 300  # Sync every 5 minutes
        done
    volumeMounts:
      - name: dags
        mountPath: /opt/airflow/dags
```

## Developer Workflow

### Adding a New Job

1. Create a new job module following the convention:

```python
# packages/my_package/jobs/my_new_job.py

def entrypoint(argv: List[str]) -> int:
    # Implementation
    return 0

JOB = (entrypoint, "My new job description")
```

2. Deploy your code (commit & push)

3. The control plane automatically:
   - Discovers the new job
   - Generates a DAG file
   - Makes it available in Airflow UI

**No manual DAG creation required!**

### Job Appears in Airflow

After sync, your job will appear in the Airflow UI:

- **DAG ID**: `my_package_my_new_job`
- **Description**: "My new job description"
- **Tags**: `my_package`, `etl`, `auto-generated`
- **Schedule**: Manual trigger (click "Trigger DAG" to run)

### Passing Arguments to Jobs

Use Airflow's DAG run configuration:

```python
# In Airflow UI or API
dag_run_conf = {
    "args": ["--option", "value"]
}
```

The control plane passes these to your job's entrypoint function.

## Testing

### Unit Tests

```bash
cd packages/airflow_control_plane
python -m unittest discover tests/unit -v
```

### Integration Test

```bash
# Discover jobs
airflow-control-plane discover --packages-root ./packages

# Generate DAGs
airflow-control-plane generate --packages-root ./packages --dags-dir /tmp/test-dags

# Verify DAGs were created
ls -la /tmp/test-dags/
```

## Architecture

### Components

1. **Job Discovery** (`discovery/scanner.py`)
   - Scans all packages for jobs
   - Uses `etl_core.jobs.discover_package_jobs`
   - Returns structured job metadata

2. **DAG Generator** (`dag_generator/generator.py`)
   - Generates Airflow DAG Python files
   - Creates standardized DAG definitions
   - Handles stale DAG cleanup

3. **CLI** (`cli/main.py`)
   - User-facing commands
   - Orchestrates discovery and generation
   - Provides feedback and error handling

### Design Principles

- **Convention over Configuration**: Jobs use existing `JOB` tuple convention
- **Zero-Touch Deployment**: Developers don't interact with Airflow directly
- **Fail-Safe**: Discovery failures don't crash the entire sync process
- **Idempotent**: Can run sync multiple times safely

## Deployment

### Building the Docker Image

```bash
docker build -f docker/airflow-control-plane.Dockerfile -t etl-airflow-control-plane .
```

### Kubernetes Deployment

See `infra/airflow_control_plane/` for:
- Terraform configuration
- Kubernetes manifests
- Deployment scripts

### CI/CD Integration

Add to your CI pipeline:

```yaml
# .github/workflows/deploy.yml
- name: Sync Airflow DAGs
  run: |
    airflow-control-plane sync \
      --packages-root ./packages \
      --dags-dir /opt/airflow/dags
```

## Troubleshooting

### DAG Not Appearing in Airflow

1. Check if job was discovered:
   ```bash
   airflow-control-plane discover
   ```

2. Verify DAG file was generated:
   ```bash
   ls -la /opt/airflow/dags/*_dag.py
   ```

3. Check Airflow logs for import errors:
   ```bash
   airflow dags list-import-errors
   ```

### Job Failing in Airflow

1. Check the generated DAG file has correct imports
2. Verify `ETL_PACKAGES_ROOT` is set correctly
3. Ensure all dependencies are installed in Airflow environment

### Stale DAGs Not Removed

Run sync with explicit clean:

```bash
airflow-control-plane sync --clean
```

## Future Enhancements

- **Custom Schedules**: Support job-level schedule configuration
- **Dependencies**: Define job dependencies (DAG chains)
- **Notifications**: Slack/email alerts for job failures
- **Metadata**: Extended job metadata (SLAs, owners, documentation)
- **Dynamic Arguments**: Template arguments from Airflow variables/connections

## Related Documentation

- [ETL Core Jobs Convention](../etl_core/README.md)
- [Airflow Documentation](https://airflow.apache.org/docs/)
- [Package Structure Guide](../../README.md)
