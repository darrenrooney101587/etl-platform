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

variable "kubeconfig_path" {
  description = "Path to kubeconfig for the Kubernetes provider (optional). If empty, the provider will use in-cluster config or default kubeconfig."
  type        = string
  default     = "~/.kube/config"
}

variable "kubeconfig_context" {
  description = "Kubeconfig context name to use for Kubernetes provider (optional)."
  type        = string
  default     = ""
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
