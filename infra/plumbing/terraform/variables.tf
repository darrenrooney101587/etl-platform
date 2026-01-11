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

variable "name_prefix" {
  description = "Name prefix used for tagging and resource names"
  type        = string
  default     = "etl-platform"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "List of public subnet CIDRs"
  type        = list(string)
  default     = ["10.0.0.0/24", "10.0.1.0/24"]
}

variable "private_subnet_cidrs" {
  description = "List of private subnet CIDRs"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
