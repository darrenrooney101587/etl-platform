# Airflow DAG Distribution Architecture

This document describes the architecture for deploying Airflow DAGs from independent packages without rebuilding the Airflow control plane.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Components](#components)
- [DAG Distribution Flow](#dag-distribution-flow)
- [Benefits](#benefits)
- [Constraints and Guarantees](#constraints-and-guarantees)

## Overview

The ETL platform uses **S3-based DAG distribution** to enable independent package deployments. This pattern allows each package (e.g., `pipeline_processing`, `reporting_seeder`) to register new Airflow jobs without rebuilding or redeploying the Airflow control plane.

### Key Principles

1. **DAGs are deployment artifacts**: Generated in CI and published to S3
2. **Control plane runs continuously**: Scheduler and webserver never restart for job changes
3. **Native Airflow discovery**: Uses standard DAG parsing cycle (no custom schedulers)
4. **Container-based execution**: Jobs run via `KubernetesPodOperator` in separate pods
5. **Package isolation**: Each package owns its DAG prefix in S3

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CI/CD Pipeline                          │
│  ┌────────────┐       ┌────────────────┐      ┌─────────────┐  │
│  │  Package   │──────▶│  DAG Generator │─────▶│  S3 Bucket  │  │
│  │   Build    │       │   & Validator  │      │             │  │
│  └────────────┘       └────────────────┘      └─────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                                        │
                                                        │ S3 Sync
                                                        │
┌─────────────────────────────────────────────────────▼───────────┐
│                    Airflow Control Plane (EKS)                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Scheduler Pod                                         │     │
│  │  ┌──────────────────┐        ┌────────────────────┐   │     │
│  │  │   Airflow        │        │   DAG Sync         │   │     │
│  │  │   Scheduler      │        │   Sidecar          │   │     │
│  │  │                  │        │   (aws s3 sync)    │   │     │
│  │  │  Parses DAGs     │◀───────│                    │   │     │
│  │  │  from /opt/      │        │   S3 → Local FS    │   │     │
│  │  │  airflow/dags    │        │   Every 30s        │   │     │
│  │  └──────────────────┘        └────────────────────┘   │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Webserver Pod                                         │     │
│  │  (UI for DAG monitoring and triggering)                │     │
│  └────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
                                  │
                                  │ KubernetesPodOperator
                                  │
┌─────────────────────────────────▼─────────────────────────────┐
│                      EKS etl-jobs Namespace                   │
│  ┌──────────────────┐       ┌──────────────────────────┐     │
│  │  pipeline-processing   │       │  reporting-seeder        │     │
│  │  Job Pod         │       │  Job Pod                 │     │
│  │  (runs once)     │       │  (runs once)             │     │
│  └──────────────────┘       └──────────────────────────┘     │
└───────────────────────────────────────────────────────────────┘
```

## Components

### 1. S3 DAG Bucket

**Purpose**: Centralized storage for all Airflow DAG files.

**Structure**:
```
s3://<bucket>/<env>/
├── pipeline_processing/
│   ├── dags/
│   │   └── pipeline_processing_example_job.py
│   └── metadata.json (optional)
└── reporting_seeder/
    ├── dags/
    │   ├── reporting_seeder_refresh_all.py
    │   └── reporting_seeder_refresh_agency.py
    └── metadata.json (optional)
```

**Isolation Rules**:
- Each package has write access only to its own prefix: `<env>/<package>/`
- Airflow has read-only access to the entire bucket
- DAG filenames must be unique across all packages

### 2. DAG Sync Sidecar

**Purpose**: Continuously sync DAGs from S3 to the scheduler's filesystem.

**Implementation**: Runs as a sidecar container in the Airflow scheduler pod.

**Behavior**:
- Runs `aws s3 sync` every 30 seconds
- Syncs from `s3://<bucket>/<env>/` to `/opt/airflow/dags/`
- Uses `--delete` flag to remove DAGs that are deleted in S3
- Uses `--exact-timestamps` for precise change detection
- Logs all sync operations for debugging

**Configuration**:
- `DAG_BUCKET`: S3 bucket name
- `ENVIRONMENT`: dev, staging, or prod
- `DAG_SYNC_INTERVAL`: Sync frequency in seconds (default: 30)

### 3. Airflow Scheduler

**Purpose**: Discovers and schedules DAGs.

**Configuration**:
- `AIRFLOW__CORE__DAGS_FOLDER`: `/opt/airflow/dags`
- `AIRFLOW__SCHEDULER__DAG_DIR_LIST_INTERVAL`: 30 seconds
- `AIRFLOW__CORE__LOAD_EXAMPLES`: False

**Behavior**:
- Parses DAGs from `/opt/airflow/dags` every 30 seconds
- Discovers new DAGs automatically without restarts
- Handles DAG parsing errors in isolation (one bad DAG doesn't break others)

### 4. airflow-dag-publisher Package

**Purpose**: CLI tool for generating and publishing DAGs to S3.

**Key Features**:
- Generates DAG files from Jinja2 templates
- Validates DAG syntax and naming conventions
- Publishes DAGs to S3 with safety checks
- Prevents cross-package overwrites

**Commands**:
```bash
# Generate a DAG file
airflow-dag-publisher generate \
  --package-name pipeline_processing \
  --dag-id pipeline_processing_example \
  --job-name example_job \
  --image-tag 123.dkr.ecr.../pipeline-processing:v1.0.0 \
  --output /tmp/dag.py

# Validate a DAG file
airflow-dag-publisher validate \
  --package-name pipeline_processing \
  --dag-file /path/to/dag.py

# Publish DAGs to S3
airflow-dag-publisher publish \
  --bucket etl-airflow-dags-dev \
  --environment dev \
  --package-name pipeline_processing \
  --dag-path ./airflow_dags

# List published DAGs
airflow-dag-publisher list \
  --bucket etl-airflow-dags-dev \
  --environment dev \
  --package-name pipeline_processing
```

## DAG Distribution Flow

### 1. Development

1. Developer writes or modifies a DAG in `packages/<package>/airflow_dags/`
2. DAG follows the `KubernetesPodOperator` pattern (see templates)
3. DAG ID follows convention: `<package_name>_<dag_name>`

### 2. CI/CD

1. Package CI pipeline runs (e.g., on merge to main)
2. Container image is built and pushed to ECR
3. DAG generation step runs:
   - Validates DAG syntax and structure
   - Injects image tag into DAG files
   - Publishes DAGs to S3 under `<env>/<package>/dags/`

### 3. Discovery

1. DAG sync sidecar detects changes in S3 (within 30 seconds)
2. Sidecar syncs new/updated DAGs to `/opt/airflow/dags/`
3. Airflow scheduler parses DAGs (within 30 seconds)
4. New DAG appears in Airflow UI automatically

### 4. Execution

1. DAG is triggered (scheduled or manual)
2. `KubernetesPodOperator` creates a new pod in the `etl-jobs` namespace
3. Pod runs the package container image with specified command
4. Pod logs are streamed to Airflow
5. Pod is deleted after completion

## Benefits

### Independent Deployments

- Packages deploy on their own schedule
- No coordination required with Airflow control plane
- No shared release cycles

### Isolation

- Package failures are isolated (bad DAG doesn't break Airflow)
- Each package has its own S3 prefix
- Each job runs in its own pod with its own resources

### Scalability

- Airflow scheduler never handles job execution logic
- Jobs scale horizontally via Kubernetes
- S3 provides unlimited DAG storage

### Operability

- DAG changes are visible in S3 and Airflow logs
- Easy rollback via S3 versioning
- Clear ownership and blast radius

### Development Velocity

- No Airflow image rebuilds required
- No Airflow pod restarts required
- CI/CD is simple and fast

## Constraints and Guarantees

### Constraints

1. **DAG IDs must be globally unique** across all packages
2. **DAGs must be deterministic and idempotent** (safe to re-parse)
3. **DAGs must not import package code** (scheduler doesn't have it)
4. **Package CI must have write access** to its S3 prefix only
5. **Sync latency** is 30-60 seconds (sync interval + parse interval)

### Guarantees

1. **Control plane never restarts** for job changes
2. **Native Airflow behavior** (no custom schedulers or hacks)
3. **Atomic DAG updates** (via S3 put-object semantics)
4. **Read-only DAG filesystem** from Airflow's perspective
5. **No cross-package coupling** (isolated DAG publishing)

## Anti-Patterns (DO NOT IMPLEMENT)

❌ **Monolithic DAG** that dynamically schedules jobs  
❌ **Runtime job polling loops** in DAGs  
❌ **Airflow API calls** for DAG registration  
❌ **Source code access** in scheduler (all logic in containers)  
❌ **Control plane image rebuilds** for job changes  

## Next Steps

- See [DEPLOYMENT.md](DEPLOYMENT.md) for deployment instructions
- See [OPERATIONS.md](OPERATIONS.md) for operational guidance
- See example DAGs in `packages/*/airflow_dags/`
