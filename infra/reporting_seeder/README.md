# reporting_seeder infra

This stack provisions a dedicated EKS cluster for `reporting_seeder`, pulling shared VPC/subnet outputs from `infra/plumbing` (foundation_network). It also supports local dev via Docker + the shared Postgres on host 5432.

## Prereqs
- `infra/plumbing` applied (VPC/subnets/NAT outputs available).
- AWS credentials with rights to create EKS/ECR/IAM.
- Docker + kubectl installed locally.

## Quick start
```bash
cd infra/reporting_seeder
./scripts/manage.sh init
./scripts/manage.sh apply
```

Update image fast path:
```bash
cd infra/reporting_seeder
./scripts/manage.sh update-image
```

Destroy (danger):
```bash
cd infra/reporting_seeder
./scripts/manage.sh destroy
```

## Local dev
- Use `docker/reporting-seeder.Dockerfile` to build/run locally against the shared Postgres on host `localhost:5432`.
- Place package env in `packages/reporting_seeder/.env` (see `.env.example`).

## Notes
- Terraform files live under `infra/reporting_seeder/terraform` (not included here; follow file_processing pattern).
- K8s namespace/deployment default to `reporting-seeder`; adjust in `scripts/manage.sh` if needed.
