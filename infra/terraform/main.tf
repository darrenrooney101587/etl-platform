terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type        = string
  description = "AWS region to deploy into"
  default     = "us-east-1"
}

variable "bucket_name" {
  type        = string
  description = "S3 bucket clients deliver into"
}

variable "sqs_queue_name" {
  type        = string
  description = "Name of SQS queue for S3 notifications"
  default     = "file-monitoring-events"
}

resource "aws_sqs_queue" "file_events" {
  name                       = var.sqs_queue_name
  message_retention_seconds  = 1209600
  visibility_timeout_seconds = 300
}

resource "aws_sqs_queue_policy" "allow_s3" {
  queue_url = aws_sqs_queue.file_events.id
  policy    = data.aws_iam_policy_document.s3_to_sqs.json
}

data "aws_iam_policy_document" "s3_to_sqs" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    actions = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.file_events.arn]

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:s3:::${var.bucket_name}"]
    }
  }
}

resource "aws_s3_bucket_notification" "file_events" {
  bucket = var.bucket_name

  queue {
    queue_arn     = aws_sqs_queue.file_events.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = ""
  }
}

resource "aws_cloudwatch_event_rule" "sweeper" {
  name                = "file-monitoring-sweeper"
  schedule_expression = "rate(5 minutes)"
}

# These are placeholders showing how to hook a containerized consumer and sweeper.
resource "aws_cloudwatch_event_target" "sweeper_target" {
  rule      = aws_cloudwatch_event_rule.sweeper.name
  arn       = aws_sqs_queue.file_events.arn
  input     = jsonencode({ action = "RUN_SWEEPER" })
  input_path = null
}
