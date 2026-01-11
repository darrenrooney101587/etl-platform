This small Terraform module provisions an *on-demand* AWS RDS PostgreSQL 15 instance for ad-hoc development or testing.

Usage (example):

```hcl
module "on_demand_postgres" {
  source = "./infra/postgres"

  aws_region   = "us-gov-west-1"
  environment  = "dev-on-demand"
  db_name      = "etl_dev"
  db_username  = "etl_admin"
  db_password  = "" # leave empty to auto-generate
  db_instance_class = "db.t4g.small"
  db_allocated_storage = 20
  public_access = false
}
```

Quick steps:

1. Ensure your AWS credentials are configured in the environment (profile or env vars).
2. From the repository root run Terraform against the `terraform` subdirectory for this stack:

```bash
# option A: use -chdir
terraform -chdir=infra/postgres/terraform init
terraform -chdir=infra/postgres/terraform apply

# option B: cd into the terraform folder
cd infra/postgres/terraform
terraform init
terraform apply -auto-approve
```

3. On success Terraform will output `db_endpoint`, `db_port`, `db_username`, and `db_password` (if generated).

Notes and warnings:

- This module is intentionally opinionated to be simple: it can create a minimal VPC and subnets if you don't provide an existing VPC/subnets.
- It is designed for **ad-hoc** use; it sets `skip_final_snapshot = true` and `deletion_protection = false` for convenience. Be cautious when using in production.
- The RDS instance is created with `engine_version = "15.4"` (Postgres 15). You can change this in `main.tf` if you need a specific minor version.
