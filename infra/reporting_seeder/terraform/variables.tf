variable "region" {
  description = "AWS region"
  type        = string
}

variable "foundation_state_bucket" {
  description = "S3 bucket holding foundation_network terraform state"
  type        = string
}

variable "foundation_state_key" {
  description = "Key for foundation_network terraform state"
  type        = string
}

variable "foundation_state_region" {
  description = "Region for foundation_network terraform state"
  type        = string
}

variable "name_prefix" {
  description = "Name prefix for resources"
  type        = string
  default     = "reporting-seeder"
}

variable "image" {
  description = "Container image for reporting_seeder"
  type        = string
}

variable "db_host" {
  description = "Database host"
  type        = string
}

variable "db_port" {
  description = "Database port"
  type        = number
  default     = 5432
}

variable "db_name" {
  description = "Database name"
  type        = string
}

variable "db_user" {
  description = "Database user"
  type        = string
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "cron_schedule" {
  description = "Cron expression for daily refresh"
  type        = string
  default     = "0 8 * * *"
}
