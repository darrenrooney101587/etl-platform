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

variable "environment" {
  description = "Logical environment name (used for tags/identifiers)"
  type        = string
  default     = "on-demand"
}

variable "db_name" {
  description = "Postgres database name"
  type        = string
  default     = "etl_test"
}

variable "db_username" {
  description = "Master DB username"
  type        = string
  default     = "etl_admin"
}

variable "db_password" {
  description = "Master DB password; if empty a random password will be generated"
  type        = string
  default     = ""
  sensitive   = true
}

variable "db_allocated_storage" {
  description = "Allocated storage (GB)"
  type        = number
  default     = 20
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.small"
}

variable "vpc_id" {
  description = "Optional existing VPC id. If empty, module will create a minimal VPC for the DB."
  type        = string
  default     = ""
}

variable "subnet_ids" {
  description = "Optional list of subnet IDs (must be private) for RDS subnets. If empty and vpc_id provided, module will try to auto-select subnets. If empty and vpc_id not provided, module creates a small VPC and subnets."
  type        = list(string)
  default     = []
}

variable "public_access" {
  description = "If true, RDS will allow public accessibility. Defaults to false."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags to apply"
  type        = map(string)
  default     = {}
}
