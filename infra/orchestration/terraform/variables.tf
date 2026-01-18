variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-gov-west-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod"
  }
}

variable "dag_bucket_name" {
  description = "S3 bucket name for Airflow DAGs"
  type        = string
  default     = ""
}

variable "vpc_id" {
  description = "VPC ID where Airflow will be deployed"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Airflow pods"
  type        = list(string)
}

variable "eks_cluster_name" {
  description = "EKS cluster name"
  type        = string
}

variable "enable_bucket_versioning" {
  description = "Enable versioning on the DAG bucket"
  type        = bool
  default     = true
}

variable "dag_bucket_lifecycle_days" {
  description = "Number of days to retain old DAG versions"
  type        = number
  default     = 90
}
