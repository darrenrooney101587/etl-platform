locals {
  common_tags = {
    ManagedBy   = "terraform"
    Component   = var.app_name
    Environment = var.environment
  }
}

resource "aws_ecs_cluster" "this" {
  name = "${var.app_name}-${var.environment}"
  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/${var.app_name}/${var.environment}/api"
  retention_in_days = 14
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/${var.app_name}/${var.environment}/worker"
  retention_in_days = 14
  tags              = local.common_tags
}

data "aws_iam_policy_document" "task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "${var.app_name}-${var.environment}-execution"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task_role" {
  name               = "${var.app_name}-${var.environment}-task"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "task_secrets" {
  count = var.slack_secret_arn != "" ? 1 : 0

  name   = "${var.app_name}-${var.environment}-secrets"
  role   = aws_iam_role.task_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.slack_secret_arn
      }
    ]
  })
}

resource "aws_sqs_queue" "notifications_dlq" {
  count = var.sqs_enabled ? 1 : 0
  name  = "${var.app_name}-${var.environment}-notifications-dlq"
  tags  = local.common_tags
}

resource "aws_sqs_queue" "notifications" {
  count = var.sqs_enabled ? 1 : 0
  name  = "${var.app_name}-${var.environment}-notifications"
  tags  = local.common_tags

  visibility_timeout_seconds = var.sqs_visibility_timeout

  redrive_policy = var.sqs_enabled ? jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notifications_dlq[0].arn
    maxReceiveCount     = 5
  }) : null
}

resource "aws_iam_role_policy" "task_queue_access" {
  count = var.sqs_enabled ? 1 : 0

  name = "${var.app_name}-${var.environment}-sqs"
  role = aws_iam_role.task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = [
          aws_sqs_queue.notifications[0].arn,
          aws_sqs_queue.notifications_dlq[0].arn,
        ]
      }
    ]
  })
}

locals {
  queue_env = var.sqs_enabled ? [
    {
      name  = "NOTIFICATION_QUEUE_URL"
      value = aws_sqs_queue.notifications[0].id
    }
  ] : []
}

locals {
  slack_secret = var.slack_secret_arn != "" ? [
    {
      name      = "SLACK_BOT_TOKEN"
      valueFrom = var.slack_secret_arn
    }
  ] : []
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.app_name}-api-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task_role.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = var.image_uri_api
      essential = true
      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]
      environment = concat([
        { name = "DATABASE_URL", value = var.database_url },
        { name = "APP_BASE_URL", value = var.app_base_url },
        { name = "INTERNAL_INGEST_TOKEN", value = var.internal_ingest_token },
      ], local.queue_env)
      secrets = local.slack_secret
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }
      command = ["python", "-m", "observability.server"]
    }
  ])

  tags = local.common_tags
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.app_name}-worker-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task_role.arn

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = var.image_uri_worker
      essential = true
      environment = concat([
        { name = "DATABASE_URL", value = var.database_url },
        { name = "APP_BASE_URL", value = var.app_base_url },
        { name = "INTERNAL_INGEST_TOKEN", value = var.internal_ingest_token },
      ], local.queue_env)
      secrets = local.slack_secret
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.worker.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "worker"
        }
      }
      command = ["python", "-m", "observability.worker", "--interval-minutes", "15"]
    }
  ])

  tags = local.common_tags
}

resource "aws_ecs_service" "api" {
  name            = "${var.app_name}-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.subnet_ids
    security_groups = var.security_group_ids
    assign_public_ip = false
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
  tags                               = local.common_tags
}

resource "aws_ecs_service" "worker" {
  name            = "${var.app_name}-worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.subnet_ids
    security_groups = var.security_group_ids
    assign_public_ip = false
  }

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
  tags                               = local.common_tags
}

resource "aws_iam_role" "events" {
  count = var.schedule_expression != "" ? 1 : 0

  name               = "${var.app_name}-${var.environment}-events"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "events" {
  count = var.schedule_expression != "" ? 1 : 0

  name = "${var.app_name}-${var.environment}-events-policy"
  role = aws_iam_role.events[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecs:RunTask"]
        Resource = [aws_ecs_task_definition.worker.arn]
      },
      {
        Effect = "Allow"
        Action = ["iam:PassRole"]
        Resource = [
          aws_iam_role.task_execution.arn,
          aws_iam_role.task_role.arn,
        ]
      }
    ]
  })
}

resource "aws_cloudwatch_event_rule" "digest" {
  count               = var.schedule_expression != "" ? 1 : 0
  name                = "${var.app_name}-${var.environment}-digest"
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "digest" {
  count = var.schedule_expression != "" ? 1 : 0

  rule      = aws_cloudwatch_event_rule.digest[0].name
  target_id = "worker-digest"
  arn       = aws_ecs_cluster.this.arn
  role_arn  = aws_iam_role.events[0].arn

  ecs_target {
    task_count          = 1
    task_definition_arn = aws_ecs_task_definition.worker.arn
    launch_type         = "FARGATE"
    network_configuration {
      subnets         = var.subnet_ids
      security_groups = var.security_group_ids
      assign_public_ip = false
    }
  }
}

output "cluster_id" {
  value = aws_ecs_cluster.this.id
}

output "api_service_name" {
  value = aws_ecs_service.api.name
}

output "worker_service_name" {
  value = aws_ecs_service.worker.name
}

output "sqs_queue_url" {
  value       = var.sqs_enabled ? aws_sqs_queue.notifications[0].id : ""
  description = "Notification queue URL (when enabled)"
}
