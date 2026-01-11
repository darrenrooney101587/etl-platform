terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.21"
    }
  }
  backend "s3" {
    # Configure via terraform init -backend-config
  }
}

provider "aws" {
  region = var.region
}

# Assume we import cluster kubeconfig out-of-band; kubernetes provider configured via env (KUBECONFIG)
provider "kubernetes" {}
