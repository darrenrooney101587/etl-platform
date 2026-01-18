# infra/ — Infrastructure layout and rationale

This document explains why infrastructure code lives under `infra/`, how shared resources are organized, how `infra/local/` is used for developer testing, and the relationship between `packages/` and `infra/`.

Goals
- Keep infrastructure code co-located with the repository so teams can reason about deployable units and their platform dependencies.
- Provide per-package infrastructure stacks so packages can be deployed independently (no shared terraform modules that create coupling).
- Centralize foundational networking and platform-level resources once (shared VPCs, NAT/IGW, logging) and consume their outputs in per-package stacks.
- Make local development reproducible via `infra/local/` helpers (LocalStack, local Docker, helper scripts).

Top-level layout (convention)
- `infra/plumbing/` or `infra/foundation_network/` — foundational stacks that must be applied once per environment. Examples: shared VPC, subnets, NAT/IGW, DNS, central ECR, logging and monitoring sinks.
- `infra/<module>/` — per-module terraform + k8s manifests + helper scripts. Each package that is deployable should have a matching infra folder (for example: `infra/file_processing/`, `infra/data_pipeline/`, `infra/reporting_seeder/`).
  - `scripts/` — terraform lifecycle helpers: `manage.sh`, `ecr_put.sh`, `setup_localstack.sh` (module-specific wrapper). These are required by convention.
  - `terraform/` — module terraform code (state backends, providers configured to consume foundation outputs).
  - `k8s/` — Kubernetes manifests or helm charts for the module's runtime resources.
- `infra/local/` — local testing helpers (LocalStack setup, docker-compose overrides, seeded local data). Intended for developer iteration and CI where Terraform/EKS are not available.

Why per-module infra?
- Isolation: each deployable unit owns its infra lifecycle, reducing blast radius and allowing different teams to iterate independently.
- Explicit dependencies: modules declare exactly which foundation outputs they consume (subnet ids, security groups, IAM roles), avoiding implicit cross-module coupling.
- Reproducibility: infra for a module is versioned alongside the package implementation and CI pipeline that builds the package image.

Foundation-first rule
- The foundational networking stack under `infra/plumbing/` (foundation network, shared services) should be applied once per environment before any per-module stacks. Per-module stacks expect these outputs to be available and wired into their Terraform inputs.

Shared resources and the "shared directory"
- Some resources are inherently shared (VPCs, NAT, DNS, central ECR, logging/monitoring). These live under `infra/plumbing/`.
- Outputs from the foundation stack are the inputs for per-module stacks. Use an explicit mechanism to pass outputs (terraform remote state outputs, exported artifacts, or CI-injected variables).
- The repo may include a `infra/shared/` or `infra/plumbing/outputs/` helper that documents or centralizes expected outputs — but the canonical ground-truth is the applied Terraform state (remote state bucket).

Safety & governance patterns
- Do not reference other modules' terraform state directly in code — consume explicit outputs only.
- Avoid copying another module's terraform into your module; instead add a clear dependency on foundation outputs.
- Keep secrets out of terraform modules in plaintext. Use secrets managers (Secrets Manager, SSM Parameter Store) and inject via CI/terraform remote state variables or Kubernetes Secrets.

Local development (`infra/local/`)
- Purpose: fast iteration loop when you don't have an EKS cluster or remote AWS resources available.
- Typical contents:
  - LocalStack helpers to emulate S3, ECR, SQS, etc.
  - Docker-compose and example env files that mirror production environment variables (but do not contain secrets).
  - Seed data used for local tests and previews.
- Conventions:
  - `infra/local/scripts/setup_localstack.sh` should be the canonical entrypoint for local environment setup.
  - Local infra scripts should be idempotent and safe to run repeatedly.

packages/ ↔ infra/ relationship
- One-to-one by intention: for each deployable package under `packages/<name>/` there should be a corresponding `infra/<name>/` that knows how to deploy that package's runtime resources.
- Responsibilities:
  - Package (`packages/<name>/`) owns code, image build, DAG generation (if applicable), and package-level CI.
  - Infra (`infra/<name>/`) owns Terraform, k8s manifests, service accounts, and any infra-level CI steps (e.g., ECR push hooks, image promotion scripts).
- CI integration pattern:
  1. Package CI builds container image and publishes to ECR (or other registry).
  2. Package CI runs package-level tests and DAG generation (if relevant) and uploads artifacts (DAGs) to the deployment artifact store (e.g., S3 DAG bucket).
  3. Infra CI (or a separate deploy stage) consumes the image tag and foundation outputs, then applies `infra/<name>/terraform` and deploys Kubernetes manifests.

Shared deployment artifacts
- Some artifacts are shared across the platform (Airflow DAGs bucket, shared S3 buckets, common ECR repo). Treat these as platform-level artifacts produced by package CI and consumed by runtime components.
- Document the artifact contract (naming conventions, prefixes, ACLs) in `infra/README.md` or the relevant infra module.

Operational notes
- Terraform state: store remote backend state (S3 + DynamoDB for locks) per module to avoid accidental state collisions. Foundation stack should have its own state and not be mixed with per-module state.
- Rollouts: use blue/green or canary patterns where appropriate. Document the expected rollout strategy in the module's `infra/<module>/README.md`.
- Observability: platform-level logging, metrics, and tracing should be wired from the foundation stack so per-module stacks can rely on the same collector endpoints.

Common helper scripts (convention)
Under each `infra/<module>/scripts/` include:
- `manage.sh` — terraform lifecycle helper (init/plan/apply/destroy/outputs)
- `ecr_put.sh` — build & push container image to ECR using `container_image.txt` produced by terraform outputs
- `setup_localstack.sh` — helper that delegates to `infra/local/scripts/setup_localstack.sh` and prepares module-specific test resources

Best practices and anti-patterns
- Do: keep infra for a module co-located and explicit; consume foundation outputs; keep secrets out of repo; provide developer-friendly local scripts.
- Don't: create cross-module terraform dependencies, hard-code shared resource ids, or store secrets in repo files.

Where to find more details
- Per-module infra: `infra/<module>/README.md` (each module should document module-specific deployment steps).
- Foundation stack: `infra/plumbing/README.md` (contains guidance for applying the foundation network and expected outputs).
- Local dev: `infra/local/README.md` (how to run LocalStack, seed data, and work with dev environment).

Questions or updates
If something is missing or a module does not follow the conventions above, open a PR that:
1. Adds the missing helper scripts under `infra/<module>/scripts/`.
2. Documents the expected inputs/outputs for the module's terraform in `infra/<module>/README.md`.
