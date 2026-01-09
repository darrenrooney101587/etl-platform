locals {
  common_tags = {
    ManagedBy = "terraform"
    Component = "file-processing"
  }
}

resource "kubernetes_namespace_v1" "ns" {
  count = var.create_namespace ? 1 : 0
  metadata {
    name = var.namespace
    annotations = var.annotations
  }
}

# Service account for pods (use IRSA externally to bind AWS IAM role)
resource "kubernetes_service_account_v1" "sa" {
  metadata {
    name = var.service_account_name
    namespace = var.create_namespace ? kubernetes_namespace_v1.ns[0].metadata[0].name : var.namespace
    annotations = var.annotations
  }
}

# Deployment for the SNS listener (long-running)
resource "kubernetes_deployment_v1" "sns_listener" {
  metadata {
    name = "file-processing-sns"
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
          name  = "sns-listener"
          image = var.image
          args  = ["-m", "file_processing.cli.sns_main"]

          port {
            name = "http"
            container_port = 8080
          }

          env {
            name = "PORT"
            value = "8080"
          }

        }
      }
    }
  }
}

output "namespace" {
  value = var.create_namespace ? kubernetes_namespace_v1.ns[0].metadata[0].name : var.namespace
}

output "deployment_name" {
  value = kubernetes_deployment_v1.sns_listener.metadata[0].name
}
