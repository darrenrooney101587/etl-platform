locals {
  dag_bucket_name = var.dag_bucket_name != "" ? var.dag_bucket_name : "etl-airflow-dags-${var.environment}"
  
  airflow_service_account = "airflow"
  airflow_namespace       = "airflow"
  
  common_tags = {
    Component = "airflow-control-plane"
  }
}

resource "aws_s3_bucket" "dags" {
  bucket = local.dag_bucket_name

  tags = merge(local.common_tags, {
    Name = "Airflow DAG Bucket"
  })
}

resource "aws_s3_bucket_versioning" "dags" {
  bucket = aws_s3_bucket.dags.id

  versioning_configuration {
    status = var.enable_bucket_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "dags" {
  bucket = aws_s3_bucket.dags.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "dags" {
  bucket = aws_s3_bucket.dags.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "dags" {
  count  = var.enable_bucket_versioning ? 1 : 0
  bucket = aws_s3_bucket.dags.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = var.dag_bucket_lifecycle_days
    }
  }
}

data "aws_iam_policy_document" "airflow_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${data.aws_eks_cluster.cluster.identity[0].oidc[0].issuer}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${data.aws_eks_cluster.cluster.identity[0].oidc[0].issuer}:sub"
      values   = ["system:serviceaccount:${local.airflow_namespace}:${local.airflow_service_account}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${data.aws_eks_cluster.cluster.identity[0].oidc[0].issuer}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "airflow_service_account" {
  name               = "airflow-service-account-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.airflow_assume_role.json

  tags = local.common_tags
}

data "aws_iam_policy_document" "airflow_s3_access" {
  statement {
    sid    = "ReadDAGBucket"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListBucket",
      "s3:ListBucketVersions"
    ]
    resources = [
      aws_s3_bucket.dags.arn,
      "${aws_s3_bucket.dags.arn}/*"
    ]
  }
}

resource "aws_iam_policy" "airflow_s3_access" {
  name        = "airflow-dag-bucket-access-${var.environment}"
  description = "Allow Airflow to read DAGs from S3"
  policy      = data.aws_iam_policy_document.airflow_s3_access.json

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "airflow_s3_access" {
  role       = aws_iam_role.airflow_service_account.name
  policy_arn = aws_iam_policy.airflow_s3_access.arn
}

data "aws_iam_policy_document" "package_dag_write" {
  statement {
    sid    = "WritePackageDAGs"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:PutObjectAcl",
      "s3:DeleteObject"
    ]
    resources = [
      "${aws_s3_bucket.dags.arn}/${var.environment}/*"
    ]
  }

  statement {
    sid    = "ListDAGBucket"
    effect = "Allow"
    actions = [
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.dags.arn
    ]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.environment}/*"]
    }
  }
}

resource "aws_iam_policy" "package_dag_write" {
  name        = "package-dag-write-${var.environment}"
  description = "Allow package CI pipelines to write DAGs to S3"
  policy      = data.aws_iam_policy_document.package_dag_write.json

  tags = local.common_tags
}

data "aws_caller_identity" "current" {}

data "aws_eks_cluster" "cluster" {
  name = var.eks_cluster_name
}
