locals {
  common_tags = {
    ManagedBy = "terraform"
    Component = "file-processing"
  }
}

locals {
  discovered_vpc_id = var.vpc_id != "" ? var.vpc_id : data.aws_vpc.foundation[0].id
}

data "aws_vpc" "foundation" {
  count = var.vpc_id == "" ? 1 : 0

  filter {
    name   = "tag:Name"
    values = ["${var.foundation_name_prefix}-vpc"]
  }
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [local.discovered_vpc_id]
  }

  filter {
    name   = "tag:Name"
    values = ["${var.foundation_name_prefix}-private-*"]
  }
}

locals {
  private_subnet_ids = data.aws_subnets.private.ids
}

data "aws_iam_policy_document" "eks_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eks_cluster" {
  name               = "${var.cluster_name}-role"
  assume_role_policy = data.aws_iam_policy_document.eks_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws-us-gov:iam::aws:policy/AmazonEKSClusterPolicy"
}

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eks_node" {
  name               = "${var.cluster_name}-node-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "eks_worker" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws-us-gov:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "eks_cni" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws-us-gov:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "ecr_readonly" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws-us-gov:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_eks_cluster" "this" {
  name     = var.cluster_name
  role_arn = aws_iam_role.eks_cluster.arn

  vpc_config {
    subnet_ids = local.private_subnet_ids
  }

  tags = local.common_tags

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]
}

resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = var.node_group_name
  node_role_arn   = aws_iam_role.eks_node.arn
  subnet_ids      = local.private_subnet_ids

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  instance_types = var.node_instance_types

  tags = local.common_tags

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker,
    aws_iam_role_policy_attachment.eks_cni,
    aws_iam_role_policy_attachment.ecr_readonly,
  ]
}

# Data sources used by the Kubernetes + Helm providers (defined in providers.tf)
data "aws_eks_cluster" "this" {
  name = aws_eks_cluster.this.name

  depends_on = [aws_eks_node_group.this]
}

data "terraform_remote_state" "postgres" {
  backend = "local"
  config = {
    path = "${path.module}/../postgres_on_demand/terraform.tfstate"
  }
}

locals {
  # Use provided variable if set, otherwise try to discover from postgres_on_demand stack
  # If neither, this will be empty string
  db_host = var.db_host != "" ? var.db_host : try(data.terraform_remote_state.postgres.outputs.db_endpoint, "")
}

data "aws_eks_cluster_auth" "this" {
  name = aws_eks_cluster.this.name

  depends_on = [aws_eks_node_group.this]
}

resource "aws_sns_topic" "file_processing" {
  name = var.sns_topic_name
  tags = local.common_tags
}

data "aws_iam_policy_document" "sns_topic_policy" {
  statement {
    effect  = "Allow"
    actions = ["SNS:Publish"]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    resources = [aws_sns_topic.file_processing.arn]

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws-us-gov:s3:::${var.bucket_name}"] # hardcoded partition for now based on vars, better to use data.aws_partition
    }
  }
}

resource "aws_sns_topic_policy" "default" {
  arn    = aws_sns_topic.file_processing.arn
  policy = data.aws_iam_policy_document.sns_topic_policy.json
}

resource "aws_s3_bucket_notification" "bucket" {
  count  = var.create_s3_notifications ? 1 : 0
  bucket = var.bucket_name

  topic {
    topic_arn = aws_sns_topic.file_processing.arn
    events    = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_sns_topic_policy.default]
}

resource "kubernetes_namespace_v1" "ns" {
  count = var.create_namespace ? 1 : 0
  metadata {
    name        = var.namespace
    annotations = var.annotations
  }

  depends_on = [aws_eks_node_group.this]
}

# NOTE: The IAM Role for the Kubernetes ServiceAccount and its S3 policy are defined
# in `irsa.tf` (aws_iam_role.file_processing_sa and aws_iam_role_policy_attachment.file_processing_s3_attach).
# We intentionally do not recreate them here to avoid duplicate resource conflicts.

resource "kubernetes_service_account_v1" "sa" {
  metadata {
    name        = var.service_account_name
    namespace   = var.create_namespace ? kubernetes_namespace_v1.ns[0].metadata[0].name : var.namespace
    annotations = merge(
      var.annotations,
      {
        "eks.amazonaws.com/role-arn" = aws_iam_role.file_processing_sa.arn
      }
    )
  }

  depends_on = [aws_eks_node_group.this, aws_iam_role_policy_attachment.file_processing_s3_attach]
}

resource "kubernetes_deployment_v1" "sns_listener" {
  metadata {
    name      = "file-processing-sns"
    namespace = var.create_namespace ? kubernetes_namespace_v1.ns[0].metadata[0].name : var.namespace
    labels = {
      app = "file-processing-sns"
    }
  }

  spec {
    replicas = var.replicas
    selector {
      match_labels = {
        app = "file-processing-sns"
      }
    }

    template {
      metadata {
        labels = {
          app = "file-processing-sns"
        }
      }

      spec {
        service_account_name = var.service_account_name

        container {
          name    = "sns-listener"
          image   = var.image
          # Override the Docker ENTRYPOINT ("python -m file_processing.cli.main")
          # so we can invoke the sns_main module directly.
          command = ["python"]
          args    = ["-m", "file_processing.cli.sns_main"]

          port {
            name           = "http"
            container_port = 8080
          }

          env {
            name  = "DB_HOST"
            value = local.db_host
          }

          # Database connection config injected from Terraform variables / remote state
          env {
            name  = "DB_PORT"
            value = var.db_port
          }

          env {
            name  = "DB_NAME"
            value = var.db_name
          }

          env {
            name  = "DB_USER"
            value = var.db_user
          }

          env {
            name  = "DB_PASSWORD"
            value = var.db_password
          }

          # IRSA web identity variables so boto3/botocore can pick up credentials
          env {
            name  = "AWS_ROLE_ARN"
            value = aws_iam_role.file_processing_sa.arn
          }

          env {
            name  = "AWS_WEB_IDENTITY_TOKEN_FILE"
            value = "/var/run/secrets/eks.amazonaws.com/serviceaccount/token"
          }
        }
      }
    }
  }

  depends_on = [aws_eks_node_group.this]
}

resource "kubernetes_service_v1" "sns_listener" {
  metadata {
    name      = "sns-listener"
    namespace = var.create_namespace ? kubernetes_namespace_v1.ns[0].metadata[0].name : var.namespace
  }

  spec {
    selector = {
      app = "file-processing-sns"
    }

    port {
      name        = "http"
      port        = 80
      target_port = 8080
    }

    type = "LoadBalancer"
  }

  depends_on = [aws_eks_node_group.this]
}

resource "aws_sns_topic_subscription" "http" {
  count     = length(var.sns_endpoint_url) > 0 ? 1 : 0
  topic_arn = aws_sns_topic.file_processing.arn
  protocol  = "http"

  endpoint = var.sns_endpoint_url

  depends_on = [aws_sns_topic_policy.default]
}

output "namespace" {
  value = var.create_namespace ? kubernetes_namespace_v1.ns[0].metadata[0].name : var.namespace
}

output "deployment_name" {
  value = kubernetes_deployment_v1.sns_listener.metadata[0].name
}

output "cluster_name" {
  value = aws_eks_cluster.this.name
}

output "sns_topic_arn" {
  value = aws_sns_topic.file_processing.arn
}

output "debug_url" {
  value = var.sns_endpoint_url
}
