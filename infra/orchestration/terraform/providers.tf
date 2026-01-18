terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    # Configure via backend config file or CLI args:
    # terraform init -backend-config="bucket=terraform-state-bucket" \
    #                -backend-config="key=orchestration/terraform.tfstate" \
    #                -backend-config="region=us-gov-west-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      ManagedBy   = "Terraform"
      Module      = "airflow"
      Purpose     = "orchestration"
    }
  }
}
