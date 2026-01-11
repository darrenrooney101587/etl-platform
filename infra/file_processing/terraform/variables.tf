variable "aws_region" {
  description = "AWS region to create resources in"
  type        = string
  default     = "us-gov-west-1"
}

variable "aws_profile" {
  description = "AWS CLI profile name to use for provider authentication"
  type        = string
  default     = "etl-playground"
}

variable "foundation_name_prefix" {
  description = "Name prefix used by the foundation_network stack for tagging (e.g., etl-platform)."
  type        = string
  default     = "etl-platform"
}

variable "vpc_id" {
  description = "Optional override for the VPC ID. If empty, the VPC will be discovered by tag (Name=<foundation_name_prefix>-vpc)."
  type        = string
  default     = ""
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "file-processing-cluster"
}

variable "node_group_name" {
  description = "EKS managed node group name"
  type        = string
  default     = "file-processing-nodes"
}

variable "node_instance_types" {
  description = "EKS node group instance types"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_desired_size" {
  description = "Desired node count"
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum node count"
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum node count"
  type        = number
  default     = 3
}

variable "sns_topic_name" {
  description = "SNS topic name for file processing notifications"
  type        = string
  default     = "file-processing-topic"
}

variable "create_s3_notifications" {
  description = "If true, configure S3 bucket notifications to SNS"
  type        = bool
  default     = false
}

variable "namespace" {
  description = "Kubernetes namespace to create resources in"
  type        = string
  default     = "file-processing"
}

variable "image" {
  description = "Container image for the file-processing runtime"
  type        = string
  default     = "example.com/etl-file-processing:latest"
}

variable "replicas" {
  description = "Number of replicas for the SNS listener"
  type        = number
  default     = 2
}

variable "service_account_name" {
  description = "ServiceAccount name for pods (use IRSA for AWS permissions)"
  type        = string
  default     = "file-processing-sa"
}

variable "create_namespace" {
  description = "If true, Terraform will create the namespace"
  type        = bool
  default     = true
}

variable "annotations" {
  description = "Optional annotations for namespace or serviceaccount (map)"
  type        = map(string)
  default     = {}
}

# Declared to match values provided in terraform.tfvars
variable "bucket_name" {
  description = "Name of the S3 bucket used by some modules (provided via terraform.tfvars)."
  type        = string
  default     = ""
}

variable "sns_endpoint_url" {
  description = "URL used by SNS subscriptions to deliver notifications (provided via terraform.tfvars)."
  type        = string
  default     = ""
}

variable "db_host" {
  description = "Database host"
  type        = string
  default     = ""
}

variable "db_port" {
  description = "Database port"
  type        = string
  default     = "5432"
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = ""
}

variable "db_user" {
  description = "Database user"
  type        = string
  default     = ""
}

variable "db_password" {
  description = "Database password"
  type        = string
  default     = ""
  sensitive   = true
}

variable "oidc_thumbprint" {
  description = "Thumbprint (SHA1 hex) for the EKS OIDC provider certificate (compute with openssl)."
  type        = string
  default     = ""
}
