variable "aws_region" {
  type        = string
  description = "AWS region"
}

variable "aws_profile" {
  type        = string
  description = "Optional AWS CLI profile"
  default     = ""
}

variable "app_name" {
  type        = string
  description = "Application name (e.g., observability)"
}

variable "environment" {
  type        = string
  description = "Deployment environment (e.g., dev, prod)"
}

variable "image_uri_api" {
  type        = string
  description = "ECR image URI for the API service"
}

variable "image_uri_worker" {
  type        = string
  description = "ECR image URI for the worker service"
}

variable "cpu" {
  type        = number
  description = "Fargate task CPU units"
  default     = 512
}

variable "memory" {
  type        = number
  description = "Fargate task memory (MiB)"
  default     = 1024
}

variable "desired_count" {
  type        = number
  description = "Desired count for the API service"
  default     = 1
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnets used by ECS tasks"
}

variable "security_group_ids" {
  type        = list(string)
  description = "Security groups attached to ECS tasks"
}

variable "database_url" {
  type        = string
  description = "Database URL for the notification service"
}

variable "slack_secret_arn" {
  type        = string
  description = "Secrets Manager ARN containing Slack credentials"
  default     = ""
}

variable "sqs_enabled" {
  type        = bool
  description = "Whether to provision an SQS queue for async notifications"
  default     = false
}

variable "sqs_visibility_timeout" {
  type        = number
  description = "Visibility timeout for the primary SQS queue"
  default     = 300
}

variable "schedule_expression" {
  type        = string
  description = "Optional EventBridge schedule for daily digest (e.g., cron(0 13 * * ? *))"
  default     = ""
}

variable "app_base_url" {
  type        = string
  description = "Base URL for deep links in Slack messages"
  default     = "https://example.com"
}

variable "internal_ingest_token" {
  type        = string
  description = "Token used to protect ingestion endpoint"
  default     = ""
}
