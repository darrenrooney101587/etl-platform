# file_processing infra

> **Quick Start (2 steps):**
>
> 1) Create shared AWS network primitives (run once per environment):
> ```bash
> cd infra/foundation_network
> ./scripts/manage.sh apply
> ```
>
> 2) Provision the `file_processing` EKS cluster + SNS wiring + Kubernetes resources:
> ```bash
> cd infra/file_processing
> ./scripts/manage_cluster.sh init
> ```
>
> Update code:
> ```bash
> ./scripts/manage_cluster.sh update
> ```
>
> Tear down the `file_processing` cluster and app resources:
> ```bash
> ./scripts/manage_cluster.sh teardown
> ```

This directory provisions a dedicated **EKS cluster** for the `file_processing` runtime plus the AWS wiring it needs (SNS topic and optional S3 bucket notifications). It is designed to run **after** `infra/foundation_network`, which owns the shared VPC/subnets/NAT/IGW.

---

## What this stack manages

- EKS cluster + managed node group
- SNS topic for file processing
- Optional: S3 bucket notifications (`s3:ObjectCreated:*`) -> SNS topic
- Optional: HTTP subscription to SNS (`sns_endpoint_url`) if you provide a stable endpoint
- Kubernetes resources deployed into the cluster:
  - Namespace
  - ServiceAccount
  - Deployment (`file-processing-sns`)
  - Service (LoadBalancer)

## Key inputs

Values live in `terraform.tfvars`.

- `foundation_name_prefix`: tag prefix used to discover the foundation VPC and subnets (defaults to `etl-platform`). The stack will look for a VPC with Name `<foundation_name_prefix>-vpc` and private subnets named like `<foundation_name_prefix>-private-*`.
- `vpc_id`: optional override for the VPC id; if set, discovery by tag is skipped.
- `bucket_name`: bucket to configure notifications for
- `create_s3_notifications`: set true to enable S3 -> SNS notifications
- `sns_endpoint_url`: optional HTTP endpoint for SNS delivery

---

## Notes

- For production-grade event delivery, SNS -> SQS tends to be more reliable than SNS -> HTTP. The current stack supports SNS -> HTTP to match the existing listener.
- This stack assumes you have permissions to create EKS/IAM resources in the target AWS account.

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

## Scripts (convenience helpers)

This repository includes a small set of helper scripts in `infra/file_processing/scripts/` to perform common developer and operational tasks. Each script is intentionally narrow in scope so you can compose them in CI or call them manually.

Location: `infra/file_processing/scripts/`

Scripts provided (summary):

- `manage.sh` — Primary entrypoint for the `file_processing` Terraform stack.
  - What it does: manage the file_processing Terraform stack (EKS + SNS + K8s) and support image updates.
  - Commands:
    - `init` — terraform init
    - `plan` — terraform plan
    - `apply` — terraform apply -auto-approve
    - `destroy` — terraform destroy -auto-approve
    - `update-image` — build & push image to ECR (via `ecr_put.sh`) and then `terraform apply -var="image=..."`
    - `outputs` — show Terraform outputs
  - Example:
    ```bash
    # Initialize
    cd infra/file_processing
    ./scripts/manage.sh init

    # Build/push image and apply
    ./scripts/manage.sh update-image

    # Destroy
    ./scripts/manage.sh destroy
    ```

- `manage_cluster.sh` — Legacy/compatibility helper. Some older docs and CI may still call this script; prefer `manage.sh` going forward.

- `ecr_put.sh` — Build and push the container image to ECR.
  - What it does: ensures the ECR repository exists, logs in, builds a multi-arch image with `docker buildx`, pushes the image, and writes the pushed image URI to `infra/file_processing/container_image.txt`.
  - Used by: `manage.sh` and `manage_cluster.sh`.

- `s3_configure_notifications.sh` — Configure an S3 bucket to publish ObjectCreated events to a topic.
  - What it does: writes a temporary notification JSON and calls `aws s3api put-bucket-notification-configuration`.
  - Example:
    ```bash
    BUCKET=etl-ba-research-client-etl AWS_PROFILE=etl-playground AWS_REGION=us-gov-west-1 ./scripts/s3_configure_notifications.sh
    ```

- `sns_subscribe.sh` — Create an SNS subscription for an HTTP endpoint.
  - Example:
    ```bash
    SNS_TOPIC_ARN=arn:aws-us-gov:sns:us-gov-west-1:270022076279:file-processing-topic ENDPOINT=https://<your-host>/ AWS_PROFILE=etl-playground ./scripts/sns_subscribe.sh
    ```

- `sns_probe_listener.sh` — Quick helper to list subscriptions for a topic (used to verify listener subscription state).
  - Example:
    ```bash
    ./scripts/sns_probe_listener.sh
    ```

- `sns_set_topic_policy.sh` — Set an SNS topic policy (e.g., allow S3 to publish to a topic for a particular bucket/account).
  - Example:
    ```bash
    ACCOUNT_ID=270022076279 BUCKET=etl-ba-research-client-etl AWS_PROFILE=etl-playground ./scripts/sns_set_topic_policy.sh
    ```

Notes and best practices

- Separation of concerns: `ecr_put.sh` is responsible only for publishing an immutable artifact to your registry. Terraform (via `manage_cluster.sh`) is responsible for instructing Kubernetes to use that artifact.
- Use image digests for immutable deployments: prefer updating your Deployment to `registry/repo@sha256:<digest>` instead of a mutable tag.
- Permissions: `ecr_put.sh` requires AWS credentials that can manage ECR. `manage_cluster.sh` requires both AWS credentials and `kubectl` access to the target cluster.

---

## Troubleshooting

- "ModuleNotFoundError: No module named 'file_processing'" in containers: ensure `PYTHONPATH=/app/packages` and that the container image was built from repo root so `packages/` were copied into the image.
- If SNS delivery fails, check Access Logs on the ALB/Ingress and the listener logs for subscription confirmation errors.
- For database connectivity, ensure the RDS security group allows inbound traffic from the cluster's VPC / nodes or the bastion host.

---

If you want, I can also generate example Kubernetes manifests in this folder (actual YAML files) tuned to your cluster's IRSA and networking conventions, or add a small `docker-compose` + `ngrok` recipe for local SNS testing. Which would you like next?
