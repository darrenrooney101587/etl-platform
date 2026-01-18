// IRSA (IAM Role for ServiceAccount) resources for pipeline-processing

data "aws_partition" "current" {}

// Create OIDC provider for the EKS cluster (if not already present)
resource "aws_iam_openid_connect_provider" "eks" {
  url            = trim(data.aws_eks_cluster.this.identity[0].oidc[0].issuer, "/")
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    var.oidc_thumbprint
  ]
  tags = local.common_tags
}

locals {
  oidc_host = replace(data.aws_eks_cluster.this.identity[0].oidc[0].issuer, "https://", "")
  sa_subject = "system:serviceaccount:${var.namespace}:${var.service_account_name}"
}

# IAM role for the Kubernetes service account (web identity trust)
resource "aws_iam_role" "pipeline_processing_sa" {
  name = "${var.cluster_name}-pipeline-processing-sa"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Federated = aws_iam_openid_connect_provider.eks.arn
        },
        Action = "sts:AssumeRoleWithWebIdentity",
        Condition = {
          StringEquals = {
            ("${local.oidc_host}:sub") = local.sa_subject
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

# Least-privilege S3 access for reading objects in the bucket
resource "aws_iam_policy" "pipeline_processing_s3" {
  name        = "${var.cluster_name}-pipeline-processing-s3"
  description = "S3 read access for pipeline-processing pods (GetObject + ListBucket)"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid = "AllowListBucket",
        Effect = "Allow",
        Action = ["s3:ListBucket"],
        Resource = ["arn:${data.aws_partition.current.partition}:s3:::${var.bucket_name}"]
      },
      {
        Sid = "AllowGetObjects",
        Effect = "Allow",
        Action = ["s3:GetObject", "s3:GetObjectVersion", "s3:HeadObject"],
        Resource = ["arn:${data.aws_partition.current.partition}:s3:::${var.bucket_name}/*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "pipeline_processing_s3_attach" {
  role       = aws_iam_role.pipeline_processing_sa.name
  policy_arn = aws_iam_policy.pipeline_processing_s3.arn
}
