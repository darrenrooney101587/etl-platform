Explanation: Add an infra README describing the purpose of the folder, Kubernetes/EKS Job manifest guidance, SNS subscription notes, local dev testing (ngrok), and pointers to the on-demand Postgres terraform module. Provide example `kubectl` commands and tips for secrets and service accounts.

# file_processing infra

This directory contains infrastructure guidance and example manifests for deploying the `file_processing` runtime into a Kubernetes/EKS environment. It is intentionally small — the repo keeps application code in `packages/file_processing` and infra examples here so teams can adapt them to their own CI/CD and cluster conventions.

This README covers:
- purpose of these infra artifacts
- example Kubernetes manifests (Job and Deployment for the SNS listener)
- secrets and config recommendations
- how to test locally (ngrok) and in-cluster
- pointer to the on-demand Postgres Terraform module

---

## Purpose

The `file_processing` package is executed as either:
- short-lived EKS Jobs that run `file-processing run s3_data_quality_job ...` for individual events, or
- a long-running worker/Deployment that exposes an HTTP endpoint for SNS `Notification` POSTs (the dev SNS listener implemented at `file_processing.cli.sns_main`).

This `infra/file_processing` folder provides example manifests and pointers for both patterns so teams can pick the mode that fits their operational model.

---

## Example: EKS Job (event-driven per-file processing)

Create a Kubernetes Job spec that runs the `etl-file-processing` image with the `run s3_data_quality_job` args. Use the cluster's service account with IAM permissions to access S3 and RDS.

Example `k8s/job-s3-data-quality.yaml`:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: s3-data-quality-job
spec:
  template:
    spec:
      serviceAccountName: file-processing-sa  # create an IAM role / IRSA binding for this SA
      containers:
      - name: file-processing
        image: example.com/etl-file-processing:latest
        command: ["python", "-m", "file_processing.cli.main"]
        args: ["run", "s3_data_quality_job", "--event-json", "<EVENT_JSON>"]
        envFrom:
        - secretRef:
            name: file-processing-secrets
        - configMapRef:
            name: file-processing-config
        volumeMounts:
        - name: tmp
          mountPath: /tmp
      restartPolicy: Never
  backoffLimit: 3
```

Notes:
- Replace `<EVENT_JSON>` with appropriate event JSON or mount an events file and point to `--events-file` instead.
- Use IRSA (IAM Roles for Service Accounts) to grant S3 and RDS access.
- Keep `restartPolicy: Never` for one-off jobs. Use a Deployment for long-running services.

---

## Example: SNS HTTP listener Deployment

For a long-running listener that receives SNS POSTs directly (useful if you prefer HTTP subscription):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: file-processing-sns
spec:
  replicas: 2
  selector:
    matchLabels:
      app: file-processing-sns
  template:
    metadata:
      labels:
        app: file-processing-sns
    spec:
      serviceAccountName: file-processing-sa
      containers:
      - name: sns-listener
        image: example.com/etl-file-processing:latest
        command: ["python"]
        args: ["-m", "file_processing.cli.sns_main"]
        ports:
        - containerPort: 8080
        env:
        - name: PORT
          value: "8080"
        envFrom:
        - secretRef:
            name: file-processing-secrets
        - configMapRef:
            name: file-processing-config
```

Expose this Deployment with a Service (ClusterIP) and an Ingress/ALB with a stable HTTPS endpoint. Subscribe that HTTPS endpoint to the SNS topic in AWS (see "SNS subscription" below).

---

## ConfigMaps and Secrets

Keep non-sensitive configuration in a `ConfigMap` (S3 bucket names, destination prefixes, operator toggles). Put credentials and DB URL in a Kubernetes `Secret`.

Example `file-processing-secrets` (kubernetes secret containing DATABASE_URL):

```bash
kubectl create secret generic file-processing-secrets \
  --from-literal=DATABASE_URL='postgresql://user:password@host:5432/dbname' \
  --from-literal=AWS_ACCESS_KEY_ID='...' \
  --from-literal=AWS_SECRET_ACCESS_KEY='...'
```

Prefer IRSA to avoid long-lived AWS keys in secrets.

---

## SNS subscription notes (HTTPS)

To configure SNS -> HTTPS -> cluster:
1. Expose the SNS listener via an HTTPS load balancer / Ingress with a stable public DNS name.
2. In the AWS SNS topic console, create a subscription with protocol `HTTPS` and endpoint `https://<your-host>/`.
3. SNS will send a `SubscriptionConfirmation` message to your endpoint. The `file_processing` SNS listener auto-confirms by visiting the `SubscribeURL`.
4. After subscription is confirmed, `Notification` POSTs will be delivered to the listener. The listener wraps the SNS envelope and forwards it to the job processor.

Security:
- Use a TLS certificate from your ACM/Ingress controller.
- Optionally validate `x-amz-sns-message-type` and `x-amz-sns-signature` for strict authorization.

---

## Local testing (ngrok)

To test SNS delivery locally:
1. Run the SNS listener locally: `poetry run file-processing-sns` (or run the container with `-p 8080:8080`).
2. Start an HTTP tunnel (e.g. `ngrok http 8080`) and use the public ngrok URL as the SNS subscription endpoint.
3. Subscribe the ngrok URL in the SNS topic (HTTPS). Confirm subscription via the SubscribeURL (the listener will do this automatically if reachable).

Alternative: skip SNS and run the job directly with an event JSON:

```bash
poetry run file-processing run s3_data_quality_job -- --event-json '{"Records":[{"s3":{"bucket":{"name":"ignored"},"object":{"key":"from_client/nm_albuquerque/Officer_Detail.csv"}}}]}' --dry-run
```

Set `LOCAL_S3_ROOT=./data` in `packages/file_processing/.env` to have the job read local files instead of S3.

---

## Database (on-demand) for dev/testing

If you need a disposable Postgres for development, see the separate Terraform module at:

```
infra/postgres_on_demand
```

It provisions a PostgreSQL 15 RDS instance with minimal networking if you don't provide an existing VPC/subnets. It is intended for ad-hoc use and is **not** production-grade without customization. See that module's README for usage and teardown instructions.

---

## Troubleshooting

- "ModuleNotFoundError: No module named 'file_processing'" in containers: ensure `PYTHONPATH=/app/packages` and that the container image was built from repo root so `packages/` were copied into the image.
- If SNS delivery fails, check Access Logs on the ALB/Ingress and the listener logs for subscription confirmation errors.
- For database connectivity, ensure the RDS security group allows inbound traffic from the cluster's VPC / nodes or the bastion host.

---

If you want, I can also generate example Kubernetes manifests in this folder (actual YAML files) tuned to your cluster's IRSA and networking conventions, or add a small `docker-compose` + `ngrok` recipe for local SNS testing. Which would you like next?
