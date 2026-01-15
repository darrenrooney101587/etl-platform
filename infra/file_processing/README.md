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
> # Init the terraform working directory and create resources
> cd infra/file_processing
> ./scripts/manage.sh init
> ./scripts/manage.sh apply
> ```
>
> Update code (build/push image and update deployment):
> ```bash
> cd infra/file_processing
> ./scripts/manage.sh update-image
> ```
>
> Tear down the `file_processing` cluster and app resources:
> ```bash
> cd infra/file_processing
> ./scripts/manage.sh destroy
> ```

## Developer workflows

### A) Run the container locally (fast iteration)

The module Dockerfile lives under the package:
- `packages/file_processing/file-processing.Dockerfile`

Build it:
```bash
docker build -f packages/file_processing/file-processing.Dockerfile -t file-processing:local .
```

Run the SNS listener locally:
```bash
docker run --rm -p 8080:8080 \
  -e PYTHONUNBUFFERED=1 \
  -e PORT=8080 \
  file-processing:local \
  python -m file_processing.cli.sns_main
```

### B) LocalStack (mimic AWS actions)

Use the module wrapper script (delegates to `infra/local/scripts/setup_localstack.sh`):

```bash
cd infra/file_processing
./scripts/setup_localstack.sh host.docker.internal 8080
```

This will:
- start LocalStack (if needed)
- create a perspective-specific S3 bucket and SNS topic
- subscribe your local listener (`host.docker.internal:8080`) as an SNS HTTP endpoint

You can then publish a test SNS message (see `infra/local/scripts/setup_localstack.sh` output + `scripts/sns_test_topic.sh`).

### C) Push to `etl-playground` (AWS testing)

Terraform lifecycle:
```bash
cd infra/file_processing
./scripts/manage.sh init
./scripts/manage.sh plan
./scripts/manage.sh apply
```

Build + push image and update the running deployment:
```bash
cd infra/file_processing
./scripts/manage.sh update-image
```

Notes:
- This stack uses `aws_profile` / `aws_region` from `infra/file_processing/terraform/terraform.tfvars` (defaults: `etl-playground`, `us-gov-west-1`).
- `./scripts/ecr_put.sh` pushes the image URI referenced in `infra/file_processing/terraform/container_image.txt`.

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

## IRSA (IAM Role for ServiceAccount) — concrete steps to enable pod S3 access

The repository now includes Terraform resources that implement IRSA (OIDC provider + IAM role + least-privilege S3 policy) in `infra/file_processing/irsa.tf`.

What you saw when you ran `aws iam list-open-id-connect-providers`:

- If the output is an empty list (``{"OpenIDConnectProviderList": []}``), there is no existing OIDC provider in this AWS account for the cluster issuer. This is expected for a new cluster; Terraform will create the provider for you when you run `terraform apply`.

If you already have an OIDC provider for this cluster, import it into Terraform instead of creating a duplicate (import instructions are below).

Concrete steps (copy/paste)

1) Compute the cluster OIDC issuer and OIDC thumbprint (run locally on your macOS zsh):

```bash
# Get the issuer URL for the cluster
ISSUER_URL=$(aws eks describe-cluster \
  --name file-processing-cluster \
  --profile etl-playground \
  --region us-gov-west-1 \
  --query "cluster.identity.oidc.issuer" --output text)

echo "OIDC issuer: $ISSUER_URL"

# Compute the SHA1 thumbprint (lowercase, no colons)
HOST=${ISSUER_URL#https://}
THUMBPRINT=$(echo | openssl s_client -servername "$HOST" -connect "$HOST:443" 2>/dev/null \
  | openssl x509 -fingerprint -sha1 -noout \
  | sed 's/.*=//; s/://g' \
  | tr '[:upper:]' '[:lower:]')

echo "OIDC thumbprint: $THUMBPRINT"
```

2) Add the thumbprint to `infra/file_processing/terraform.tfvars` (one-liner):

```hcl
# infra/file_processing/terraform.tfvars
oidc_thumbprint = "<paste-the-sha1-hex-here>"
```

3) Run Terraform to create the OIDC provider, IAM role and policy, and annotate the ServiceAccount:

```bash
# from the infra directory for this stack or use the helper
cd infra/file_processing
./scripts/manage.sh init
./scripts/manage.sh apply
```

Notes on what Terraform creates
- `aws_iam_openid_connect_provider.eks` — OIDC provider for the EKS issuer (created only if one doesn't already exist).
- `aws_iam_role.file_processing_sa` — IAM role that can be assumed by the ServiceAccount via web identity.
- `aws_iam_policy.file_processing_s3` — least-privilege S3 policy scoped to `var.bucket_name`.
- `aws_iam_role_policy_attachment.file_processing_s3_attach` — attaches the policy to the role.
- The `kubernetes_service_account_v1` in `main.tf` is annotated with this role ARN so pods that use that ServiceAccount get short-lived credentials.

4) Restart the Deployment so pods pick up the ServiceAccount annotation (if necessary):

```bash
kubectl -n file-processing rollout restart deployment/file-processing-sns
kubectl -n file-processing rollout status deployment/file-processing-sns
```

5) Verify the pod assumes the role and can call AWS APIs (STS identity + S3 test):

```bash
# pick a pod
POD=$(kubectl -n file-processing get pods -l app=file-processing-sns -o jsonpath='{.items[0].metadata.name}')

# Check STS identity (should show the IRSA role ARN)
kubectl -n file-processing exec $POD -- python -c "import boto3, json; print(boto3.client('sts').get_caller_identity())"

# Quick S3 read test (adjust bucket/key as needed)
kubectl -n file-processing exec $POD -- python - <<'PY'
import boto3
s3 = boto3.client('s3', region_name='us-gov-west-1')
resp = s3.list_objects_v2(Bucket='etl-ba-research-client-etl', Prefix='from_client/nm_albuquerque/')
print('Objects found:', resp.get('KeyCount'))
PY
```

If the STS call returns a role ARN that matches `aws_iam_role.file_processing_sa`, and the S3 call succeeds, the pod can pull objects from the bucket using IRSA.

Importing an existing OIDC provider (only if one already exists)

If your account already has an OIDC provider for this cluster (check with `aws iam list-open-id-connect-providers` and `aws iam get-open-id-connect-provider --open-id-connect-provider-arn <arn>`), import it into Terraform instead of creating a new one:

```bash
# find provider ARN and import (use -chdir to target the terraform subdir)
terraform -chdir=infra/file_processing/terraform import aws_iam_openid_connect_provider.eks <provider-arn>
./scripts/manage.sh plan
```

After importing, run `./scripts/manage.sh apply` as above.

When to remove node-level S3 access

- We temporarily attach a broad S3 policy to the node role in the Terraform stack to avoid requiring IRSA immediately in some debugging workflows. After IRSA is verified, remove or comment out `aws_iam_role_policy_attachment.s3_access` in `main.tf` and run `terraform apply` to remove the node-level `AmazonS3FullAccess` attachment.

Security and best-practice notes

- Prefer narrow, prefix-scoped S3 permissions in `irsa.tf` rather than `AmazonS3FullAccess`.
- Prefer immutable image tags or image digests (`@sha256:...`) to avoid relying on mutable tags like `:latest`.
- Keep the OIDC thumbprint secret only in Terraform variables (do not commit credentials). The thumbprint itself is not sensitive but the `terraform.tfvars` file contains `db_password` which must be guarded.

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

## Local dev — LocalStack + local listener (recommended for fast iteration)

This repository includes helpers to run a full local SNS/S3 stack using LocalStack and a local SNS HTTP listener so you can exercise the same SNS -> listener -> job flow used in production without touching AWS.

Summary:
- `infra/local` contains shared local plumbing for LocalStack (docker-compose and central setup script).
- Per‑perspective wrappers live in `infra/<perspective>/setup_localstack.sh` (for example `infra/file_processing/setup_localstack.sh`).
- The local HTTP listener is `packages/file_processing/cli/sns_main.py` and the helper runner is `packages/file_processing/scripts/run_local_listener.sh`.

Quick start (copy/paste):

1) Start LocalStack:

```bash
cd infra/local
docker-compose up -d
sleep 6  # give LocalStack a few seconds to initialize
```

2) Create perspective-scoped bucket/topic and subscribe the listener endpoint (default uses `host.docker.internal:8080`):

```bash
# from repo root
infra/file_processing/scripts/setup_localstack.sh host.docker.internal 8080 | tee /tmp/localstack-setup.log
```

This creates an S3 bucket named `etl-file-processing-client-etl` and an SNS topic `file-processing-topic` and subscribes `http://host.docker.internal:8080/`.

3) Start the SNS listener locally (so LocalStack can POST to it). Run this in a dedicated terminal so you can see logs and use your IDE for breakpoints:

```bash
# from repo root
packages/file_processing/scripts/run_local_listener.sh 8080
# or directly
python -m file_processing.cli.sns_main
```

The listener binds to all interfaces (0.0.0.0) so the LocalStack container can reach it via `host.docker.internal` on macOS.

4) Verify container -> host connectivity (simulate LocalStack network reachability):

```bash
# run from host; attempts a HEAD request from a container
docker run --rm curlimages/curl:8.1.2 -sS -I http://host.docker.internal:8080/ || true
```

We added a HEAD handler to the listener so `curl -I` returns a healthy response instead of 501.

5) Publish a test SNS message to LocalStack (example):

```bash
EDGE="https://localhost:4566"  # LocalStack edge
TOPIC_ARN="arn:aws:sns:us-east-1:000000000000:file-processing-topic"

aws --no-verify-ssl --endpoint-url "$EDGE" --region us-east-1 sns publish \
  --topic-arn "$TOPIC_ARN" \
  --message '{"Records":[{"s3":{"bucket":{"name":"etl-file-processing-client-etl"},"object":{"key":"from_client/nm_albuquerque/Officer_Detail.csv"}}}]}'
```

Notes:
- The setup script auto-detects if LocalStack is serving HTTPS and adds `--no-verify-ssl` to the AWS CLI calls (LocalStack uses a self-signed cert). Seeing `InsecureRequestWarning` is expected for local dev.
- If you prefer valid TLS locally, map a LocalStack hostname (for example `localhost.localstack.cloud`) to `127.0.0.1` and set `LOCALSTACK_HOSTNAME` so cert SANs match — we can add a helper for that if you want.

6) Inspect logs:
- LocalStack: `docker-compose -f infra/local/docker-compose.yml logs --tail=200 -f`
- Listener: watch the terminal where you started `run_local_listener.sh` or run in your IDE.

Troubleshooting (common issues)

- LocalStack shows `Connection refused` when delivering to `host.docker.internal:8080`:
  - Ensure the listener is running on your host and bound to all interfaces (0.0.0.0). The provided server binds to `("", port)` which accepts connections from Docker.
  - Run the container probe command from step 4 to confirm container -> host connectivity.
  - If the probe fails, confirm Docker Desktop is running and `host.docker.internal` resolves. On Linux you may need to use your host IP or run the listener inside Docker.

- `Address already in use` when starting the listener:
  - Find and stop the process using the port: `lsof -nP -iTCP:8080 -sTCP:LISTEN`
  - Or start the listener on another port and re-run the setup wrapper with that port: `infra/file_processing/scripts/setup_localstack.sh host.docker.internal 8090` and `packages/file_processing/scripts/run_local_listener.sh 8090`.

- If you see TLS/hostname mismatch warnings, the setup script already uses `--no-verify-ssl` for LocalStack HTTPS; to avoid disabling verification, use the `LOCALSTACK_HOSTNAME` approach described above.

Per‑perspective wrappers

- `infra/file_processing/scripts/setup_localstack.sh` — calls the central `infra/local/scripts/setup_localstack.sh` with the `file_processing` perspective.
- `infra/data_pipeline/setup_localstack.sh` — similar wrapper for `data_pipeline`.

Production mapping reminder

- In production the SNS listener runs as a Deployment in EKS (see the "SNS HTTP listener Deployment" example below). Terraform in `infra/file_processing` wires the SNS topic and (optionally) the S3 notifications and subscribes the production HTTPS endpoint (the ALB/Ingress URL) instead of `host.docker.internal`.
- The local dev flow mirrors the same code path so tests are representative of production behavior.

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
  - What it does: ensures the ECR repository exists, logs in, builds a multi-arch image with `docker buildx`, pushes the image, and writes the pushed image URI to `infra/file_processing/terraform/container_image.txt`.
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

## Local database for development (Postgres)

The SNS -> listener -> job flow requires a Postgres database for lookups and run metadata. For local development you can run a lightweight Postgres container and point the listener/job at it.

1) Start a local Postgres container

```bash
# run Postgres 14 on local port 5432 with username/password 'postgres'
docker run --name local-postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=postgres -p 5432:5432 -d postgres:14
```

2) Export DB environment variables (listener process reads these when connecting)

```bash
# Option A: use DATABASE_URL
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/postgres"

# Option B: use DB_* env vars (the DatabaseClient falls back to these)
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=postgres
export DB_USER=postgres
export DB_PASSWORD=postgres
```

3) Verify you can connect (quick Python check)

```bash
python - <<'PY'
import os
import psycopg2
print('DATABASE_URL=', os.getenv('DATABASE_URL'))
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
print('Connected OK, version:', conn.server_version)
conn.close()
PY
```

If you prefer `psql`:

```bash
# Install psql client if needed (macOS: `brew install libpq` then `brew link --force libpq`)
psql "postgresql://postgres:postgres@localhost:5432/postgres" -c 'select version();'
```

4) Start the SNS listener with the DB env in the same terminal (so the process sees the variables):

```bash
# With DATABASE_URL exported above
packages/file_processing/scripts/run_local_listener.sh 8080

# or directly (ensures variables are exported in the command environment)
DB_HOST=localhost DB_PORT=5432 DB_NAME=postgres DB_USER=postgres DB_PASSWORD=postgres packages/file_processing/scripts/run_local_listener.sh 8080
```

5) Re-publish the test SNS message (LocalStack -> listener -> job)

```bash
EDGE="https://localhost:4566"
TOPIC_ARN="arn:aws:sns:us-east-1:000000000000:file-processing-topic"
aws --no-verify-ssl --endpoint-url "$EDGE" --region us-east-1 sns publish \
  --topic-arn "$TOPIC_ARN" \
  --message '{"Records":[{"s3":{"bucket":{"name":"etl-file-processing-client-etl"},"object":{"key":"from_client/nm_albuquerque/organizations/Officer_Detail.csv"}}}]}'
```

6) Notes on schema and test data

- The real job expects application-specific tables (monitoring files, runs, mappings). Running a plain Postgres instance will allow the job to connect, but the job may still fail if expected rows are missing.
- For full local parity, load a DB dump from your dev environment or run the project's migration/data seed if available. If you don't have a dump, run the job in `--dry-run` or use the unit tests' fixtures to exercise behavior.

7) Quick cleanup

```bash
docker stop local-postgres && docker rm local-postgres
```

This local Postgres approach is intended for development and debugging only. For production, use the `infra/postgres_on_demand` Terraform module or your managed RDS instance and ensure the `DATABASE_URL` (or DB_* env vars) are set in the Kubernetes Deployment/Secret so the pods can authenticate successfully.
