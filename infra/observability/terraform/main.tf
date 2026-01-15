locals {
  labels = {
    app         = var.app_name
    environment = var.environment
  }
}

resource "kubernetes_namespace" "this" {
  metadata {
    name = var.namespace
  }
}

resource "kubernetes_config_map" "job_env" {
  metadata {
    name      = "${var.app_name}-env"
    namespace = kubernetes_namespace.this.metadata[0].name
    labels    = local.labels
  }

  data = var.job_env
}

resource "kubernetes_cron_job_v1" "reminder_dispatcher" {
  metadata {
    name      = "${var.app_name}-reminder-dispatcher"
    namespace = kubernetes_namespace.this.metadata[0].name
    labels    = local.labels
  }

  spec {
    schedule          = var.reminder_schedule
    concurrency_policy = "Forbid"

    job_template {
      metadata { labels = local.labels }
      spec {
        template {
          metadata { labels = local.labels }
          spec {
            restart_policy = "Never"
            container {
              name    = "reminder-dispatcher"
              image   = var.image
              command = ["python", "-m", "observability.jobs.reminder_dispatcher"]
              env_from {
                config_map_ref {
                  name = kubernetes_config_map.job_env.metadata[0].name
                }
              }
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_cron_job_v1" "daily_digest" {
  metadata {
    name      = "${var.app_name}-daily-digest"
    namespace = kubernetes_namespace.this.metadata[0].name
    labels    = local.labels
  }

  spec {
    schedule          = var.digest_schedule
    concurrency_policy = "Forbid"

    job_template {
      metadata { labels = local.labels }
      spec {
        template {
          metadata { labels = local.labels }
          spec {
            restart_policy = "Never"
            container {
              name    = "daily-digest"
              image   = var.image
              command = ["python", "-m", "observability.jobs.daily_digest"]
              env_from {
                config_map_ref {
                  name = kubernetes_config_map.job_env.metadata[0].name
                }
              }
            }
          }
        }
      }
    }
  }
}

output "namespace" {
  value = kubernetes_namespace.this.metadata[0].name
}

output "reminder_cron_name" {
  value = kubernetes_cron_job_v1.reminder_dispatcher.metadata[0].name
}

output "digest_cron_name" {
  value = kubernetes_cron_job_v1.daily_digest.metadata[0].name
}
