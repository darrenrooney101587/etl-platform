variable "app_name" {
  type        = string
  description = "Application name (e.g., observability)"
}

variable "environment" {
  type        = string
  description = "Deployment environment (e.g., dev, prod)"
}

variable "image" {
  type        = string
  description = "OCI image for notification jobs"
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

variable "namespace" {
  type        = string
  description = "Kubernetes namespace for jobs"
  default     = "observability"
}

variable "kubeconfig_path" {
  type        = string
  description = "Path to kubeconfig used by the kubernetes provider"
  default     = "~/.kube/config"
}

variable "kubeconfig_context" {
  type        = string
  description = "Optional kubeconfig context"
  default     = ""
}

variable "reminder_schedule" {
  type        = string
  description = "Cron expression for reminder dispatcher"
  default     = "*/15 * * * *"
}

variable "digest_schedule" {
  type        = string
  description = "Cron expression for daily digest"
  default     = "0 8 * * *"
}

variable "job_env" {
  type        = map(string)
  description = "Environment variables injected into jobs"
  default     = {}
}
