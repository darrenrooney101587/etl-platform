# Airflow DAG Distribution - Operations Guide

This document covers operational procedures, debugging, and failure mode handling for the Airflow DAG distribution system.

## Table of Contents

- [Monitoring](#monitoring)
- [Common Operations](#common-operations)
- [Debugging](#debugging)
- [Failure Modes](#failure-modes)
- [Recovery Procedures](#recovery-procedures)
- [Performance Tuning](#performance-tuning)

## Monitoring

### Key Metrics

Monitor these metrics for healthy operation:

1. **DAG Sync Latency**
   - Time from S3 upload to Airflow discovery
   - Target: < 60 seconds (30s sync + 30s parse)
   - Alert if: > 2 minutes

2. **DAG Parse Success Rate**
   - Percentage of DAGs successfully parsed
   - Target: 100%
   - Alert if: < 95%

3. **S3 Sync Errors**
   - Failed S3 sync operations
   - Target: 0
   - Alert if: > 3 consecutive failures

4. **Job Execution Success Rate**
   - Percentage of successful KubernetesPodOperator runs
   - Target: > 95%
   - Alert if: < 90%

### CloudWatch Logs

Key log groups to monitor:

```bash
# Airflow scheduler logs
kubectl logs -n airflow -l component=scheduler --tail=100

# DAG sync sidecar logs
kubectl logs -n airflow -l component=scheduler -c dag-sync --tail=100

# Job execution logs (per package)
kubectl logs -n etl-jobs -l app=<package-name> --tail=100
```

### Airflow UI Metrics

Monitor via the Airflow UI:

- DAG run success/failure rates
- Task duration trends
- SLA misses
- Pool utilization (if using pools)

## Common Operations

### List All DAGs in S3

```bash
aws s3 ls s3://<bucket>/<env>/ --recursive
```

### List DAGs by Package

```bash
aws s3 ls s3://<bucket>/<env>/<package>/dags/ --recursive
```

### View DAG Content from S3

```bash
aws s3 cp s3://<bucket>/<env>/<package>/dags/<dag_file>.py -
```

### Verify DAG in Scheduler Filesystem

```bash
kubectl exec -n airflow \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- cat /opt/airflow/dags/<package>/dags/<dag_file>.py
```

### Force Immediate Sync

Restart the scheduler pod to trigger immediate sync:

```bash
kubectl rollout restart deployment/airflow-scheduler -n airflow
```

Or exec into the sidecar and run sync manually:

```bash
kubectl exec -n airflow -c dag-sync \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- aws s3 sync s3://<bucket>/<env>/ /opt/airflow/dags/ --delete
```

### Pause/Unpause a DAG

Via Airflow UI:
- Navigate to the DAG
- Toggle the pause/unpause switch

Via CLI:

```bash
kubectl exec -n airflow \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- airflow dags pause <dag_id>

kubectl exec -n airflow \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- airflow dags unpause <dag_id>
```

### Trigger a DAG Run

Via Airflow UI:
- Navigate to the DAG
- Click "Trigger DAG"

Via CLI:

```bash
kubectl exec -n airflow \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- airflow dags trigger <dag_id>
```

### View DAG Run Logs

Via Airflow UI:
- Navigate to the DAG
- Click on the DAG run
- Click on the task
- View logs

Via kubectl (for KubernetesPodOperator tasks):

```bash
# Find the job pod
kubectl get pods -n etl-jobs -l dag_id=<dag_id>

# View logs
kubectl logs -n etl-jobs <pod-name> -f
```

## Debugging

### DAG Not Appearing in Airflow

**Symptom**: DAG published to S3 but not visible in Airflow UI.

**Debug Steps**:

1. Verify DAG is in S3:
   ```bash
   aws s3 ls s3://<bucket>/<env>/<package>/dags/
   ```

2. Check DAG sync sidecar logs:
   ```bash
   kubectl logs -n airflow -l component=scheduler -c dag-sync --tail=100
   ```
   Look for sync errors or S3 access issues.

3. Verify DAG is in scheduler filesystem:
   ```bash
   kubectl exec -n airflow \
     $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
     -- ls -R /opt/airflow/dags/
   ```

4. Check scheduler logs for parse errors:
   ```bash
   kubectl logs -n airflow -l component=scheduler --tail=100 | grep -i "error\|failed"
   ```

5. Verify DAG syntax locally:
   ```bash
   cd packages/airflow_dag_publisher
   poetry run airflow-dag-publisher validate \
     --package-name <package> \
     --dag-file <path_to_dag>
   ```

**Common Causes**:
- Syntax errors in DAG file
- Missing imports (e.g., airflow providers)
- Incorrect DAG ID format
- S3 sync failure (IAM permissions)

### DAG Parsing Errors

**Symptom**: DAG appears with errors in Airflow UI.

**Debug Steps**:

1. Click on the DAG in Airflow UI to see error details

2. Check scheduler logs:
   ```bash
   kubectl logs -n airflow -l component=scheduler --tail=200 | grep "<dag_id>"
   ```

3. Validate DAG locally:
   ```bash
   python <dag_file>.py
   ```

**Common Causes**:
- Import errors (missing Python packages in Airflow image)
- Invalid Python syntax
- Circular imports
- Accessing undefined variables

### Job Pod Fails to Start

**Symptom**: KubernetesPodOperator task fails, pod doesn't start.

**Debug Steps**:

1. Check pod status:
   ```bash
   kubectl get pods -n etl-jobs -l dag_id=<dag_id>
   kubectl describe pod -n etl-jobs <pod-name>
   ```

2. Common issues:
   - Image pull errors (ECR permissions, image doesn't exist)
   - Resource quota exceeded
   - Invalid service account
   - Missing namespace

3. Verify image exists:
   ```bash
   aws ecr describe-images --repository-name <repo> --image-ids imageTag=<tag>
   ```

4. Check RBAC:
   ```bash
   kubectl get serviceaccount -n etl-jobs
   kubectl get rolebindings -n etl-jobs
   ```

### Job Execution Failures

**Symptom**: Pod starts but job exits with non-zero status.

**Debug Steps**:

1. View job logs:
   ```bash
   kubectl logs -n etl-jobs <pod-name>
   ```

2. Check exit code:
   ```bash
   kubectl get pod -n etl-jobs <pod-name> -o jsonpath='{.status.containerStatuses[0].state.terminated.exitCode}'
   ```

3. View Airflow task logs for additional context

**Common Causes**:
- Application bugs
- Missing environment variables
- Database connection failures
- S3 access issues
- Insufficient resources (OOM)

### Slow DAG Discovery

**Symptom**: DAGs take more than 60 seconds to appear.

**Debug Steps**:

1. Check sync interval:
   ```bash
   kubectl get pod -n airflow -l component=scheduler -o yaml | grep DAG_SYNC_INTERVAL
   ```

2. Check parse interval:
   ```bash
   kubectl exec -n airflow \
     $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
     -- airflow config get-value scheduler dag_dir_list_interval
   ```

3. Check S3 sync performance:
   ```bash
   kubectl logs -n airflow -l component=scheduler -c dag-sync --tail=50
   ```
   Look for slow sync times.

**Solutions**:
- Reduce `DAG_SYNC_INTERVAL` (e.g., from 30 to 15 seconds)
- Reduce `dag_dir_list_interval` (e.g., from 30 to 15 seconds)
- Use S3 Transfer Acceleration (if cross-region)

## Failure Modes

### DAG Upload Fails in CI

**Impact**: New/updated DAGs don't reach Airflow.

**Detection**:
- CI pipeline fails at DAG publish step
- Error logs in GitLab CI job

**Causes**:
- Invalid AWS credentials
- IAM policy doesn't allow write to S3 prefix
- S3 bucket doesn't exist
- Network connectivity issues

**Mitigation**:
- CI job fails fast with clear error message
- No partial writes (S3 put-object is atomic)
- Package continues to use previous DAG version

**Recovery**:
1. Fix the underlying issue (credentials, permissions, etc.)
2. Re-run the CI pipeline

### Malformed DAG Published

**Impact**: Airflow logs parse errors, DAG doesn't execute.

**Detection**:
- DAG appears with error icon in Airflow UI
- Scheduler logs show import/parse errors

**Blast Radius**:
- **Isolated**: Only affects the malformed DAG
- **Other DAGs continue to run normally**
- Airflow scheduler continues operating

**Mitigation**:
- Pre-publish validation catches most issues
- Airflow isolates parse errors per DAG file

**Recovery**:
1. Fix the DAG file locally
2. Re-run CI pipeline to publish corrected version
3. Wait for sync (30-60 seconds)
4. Verify in Airflow UI

### S3 Sync Sidecar Crashes

**Impact**: New DAGs don't sync, but existing DAGs continue to run.

**Detection**:
- Sidecar container shows `CrashLoopBackOff`
- No sync logs in past N minutes

**Causes**:
- S3 bucket deleted
- IAM role misconfigured
- Out of memory
- AWS API rate limiting

**Recovery**:

1. Check sidecar logs:
   ```bash
   kubectl logs -n airflow -l component=scheduler -c dag-sync --tail=100
   ```

2. Fix underlying issue (recreate bucket, fix IAM, etc.)

3. Restart scheduler pod:
   ```bash
   kubectl rollout restart deployment/airflow-scheduler -n airflow
   ```

### Scheduler Pod Crash

**Impact**: No DAG scheduling until pod recovers.

**Detection**:
- Scheduler pod shows `CrashLoopBackOff` or `Error`
- No DAG runs being scheduled

**Causes**:
- Out of memory
- Corrupted metadata database
- Bug in Airflow code
- Resource exhaustion

**Recovery**:

1. Check scheduler logs:
   ```bash
   kubectl logs -n airflow -l component=scheduler --tail=200
   ```

2. If OOM, increase memory limits in Helm values

3. If database issue, check PostgreSQL logs

4. Restart scheduler:
   ```bash
   kubectl rollout restart deployment/airflow-scheduler -n airflow
   ```

### All DAGs for a Package Fail

**Impact**: All jobs for one package fail.

**Detection**:
- Multiple DAG runs fail for the same package
- Job pods crash or error

**Causes**:
- Package image is broken
- Database connection issue (if package uses DB)
- AWS credentials expired
- Dependency service down

**Blast Radius**:
- **Isolated to one package**
- Other packages continue to operate

**Recovery**:

1. Identify root cause (check job pod logs)

2. If image issue, rollback to previous image tag:
   - Update DAG file with old image tag
   - Publish to S3
   - Wait for sync

3. If external dependency, fix the dependency

### S3 Bucket Deleted

**Impact**: DAG sync fails, control plane can't discover new DAGs.

**Detection**:
- Sidecar logs show 404 errors
- No new DAGs discovered

**Recovery**:

1. Recreate bucket with Terraform:
   ```bash
   cd infra/airflow/scripts
   ./manage.sh apply
   ```

2. Re-publish all DAGs from all packages:
   - Re-run CI pipelines for all packages
   - Or manually copy from backups

3. Restart scheduler to trigger full sync

## Recovery Procedures

### Full DAG Re-sync

If DAGs are out of sync between S3 and Airflow:

```bash
# Option 1: Restart scheduler pod (forces re-sync)
kubectl rollout restart deployment/airflow-scheduler -n airflow

# Option 2: Manually trigger sync in sidecar
kubectl exec -n airflow -c dag-sync \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- aws s3 sync s3://<bucket>/<env>/ /opt/airflow/dags/ --delete
```

### Rollback Package DAGs

Rollback all DAGs for a package to a previous version:

```bash
# List S3 versions
aws s3api list-object-versions \
  --bucket <bucket> \
  --prefix <env>/<package>/dags/

# Restore specific version
aws s3api copy-object \
  --copy-source <bucket>/<env>/<package>/dags/<dag_file>.py?versionId=<version_id> \
  --bucket <bucket> \
  --key <env>/<package>/dags/<dag_file>.py

# Wait for sync (30-60 seconds)
# Verify in Airflow UI
```

### Emergency: Stop All Jobs for a Package

Pause all DAGs for a package:

```bash
# Get all DAG IDs for the package
kubectl exec -n airflow \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- airflow dags list | grep "^<package>_"

# Pause each DAG
for dag_id in $(kubectl exec -n airflow \
  $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
  -- airflow dags list | grep "^<package>_" | awk '{print $1}'); do
  kubectl exec -n airflow \
    $(kubectl get pod -n airflow -l component=scheduler -o name | head -1) \
    -- airflow dags pause "$dag_id"
done
```

### Restore from S3 Versioning

If DAGs were accidentally deleted:

```bash
# Find deleted versions
aws s3api list-object-versions \
  --bucket <bucket> \
  --prefix <env>/<package>/dags/ \
  --query 'DeleteMarkers[].{Key:Key,VersionId:VersionId}'

# Remove delete marker to restore
aws s3api delete-object \
  --bucket <bucket> \
  --key <env>/<package>/dags/<dag_file>.py \
  --version-id <delete_marker_version_id>
```

## Performance Tuning

### Reduce Discovery Latency

Decrease both sync and parse intervals:

Update Helm values:

```yaml
env:
  - name: AIRFLOW__SCHEDULER__DAG_DIR_LIST_INTERVAL
    value: "15"  # Down from 30
  - name: DAG_SYNC_INTERVAL
    value: "15"  # Down from 30
```

Apply changes:

```bash
helm upgrade airflow apache-airflow/airflow \
  --namespace airflow \
  --values airflow-values.yaml
```

### Optimize S3 Sync

Use `--size-only` if timestamp checks are unreliable:

Update sidecar command in Helm values:

```yaml
command:
  - /bin/sh
  - -c
  - |
    aws s3 sync s3://<bucket>/<env>/ /opt/airflow/dags/ \
      --delete --size-only --no-progress
```

### Scale Scheduler Horizontally

For high DAG volume, run multiple schedulers:

```yaml
scheduler:
  replicas: 2  # Up from 1
```

Note: Requires Airflow 2.0+ with HA scheduler support.

## Best Practices

1. **Always validate DAGs locally before publishing**
2. **Use manual approval for production DAG publishes**
3. **Monitor sync latency and parse errors**
4. **Keep S3 versioning enabled for rollback**
5. **Document DAG dependencies and data lineage**
6. **Use tags to organize DAGs by package, priority, etc.**
7. **Set SLAs for critical DAGs**
8. **Test DAGs in dev before promoting to prod**

## Escalation

If issues persist after following this guide:

1. Check Airflow documentation: https://airflow.apache.org/docs/
2. Review Kubernetes events: `kubectl get events -n airflow --sort-by='.lastTimestamp'`
3. Engage platform team for infrastructure issues
4. File incident ticket with:
   - Symptoms and timeline
   - Logs from scheduler, sidecar, job pods
   - S3 sync status
   - Recent changes (code, config, infrastructure)
