# Placeholder Terraform for reporting_seeder stack.
# Mirrors pipeline processing pattern: cluster, IAM, namespace, deployment, scheduled job.

locals {
  tags = {
    Project = "etl-platform"
    Stack   = var.name_prefix
  }
}

# TODO: remote state data source to read foundation_network outputs
# data "terraform_remote_state" "foundation" {
#   backend = "s3"
#   config = {
#     bucket = var.foundation_state_bucket
#     key    = var.foundation_state_key
#     region = var.foundation_state_region
#   }
# }

# TODO: ECR repo for reporting-seeder
# resource "aws_ecr_repository" "repo" {
#   name                 = "${var.name_prefix}"
#   image_tag_mutability = "MUTABLE"
#   tags                 = local.tags
# }

# TODO: EKS cluster and node group (can reuse module from pipeline processing pattern)
# TODO: IAM roles/policies for service account
# TODO: kubernetes_namespace
# TODO: kubernetes_service_account
# TODO: kubernetes_deployment for reporting-seeder
# TODO: kubernetes_cron_job_v1 for daily refresh using var.cron_schedule

# TODO: Write container_image.txt output similar to pipeline processing for update-image helper
