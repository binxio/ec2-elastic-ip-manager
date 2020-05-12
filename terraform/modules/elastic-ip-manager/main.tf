terraform {
  required_version = ">= 0.12.6"
}

data "aws_region" "current" {}

# Determine the default S3 bucket name for the corresponding region
locals {
  s3_bucket = coalesce(var.s3_bucket, "binxio-public-${data.aws_region.current.name}")
}

# ---------------------------------------------------------------------------------------------------------------------
# IAM Policy and Role
# ---------------------------------------------------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "elastic_ip_manager" {
  statement {
    actions = [
      "ec2:DescribeAddresses",
      "ec2:DescribeInstances",
      "ec2:AssociateAddress",
      "ec2:DisassociateAddress",
      "tag:GetTagValues"
    ]

    resources = ["*"]
  }
}

resource "aws_iam_policy" "elastic_ip_manager" {
  name        = var.name
  description = "The policy allowing elastic-ip-manager lambda function to manage ElasticIP addresses on EC2 instances"
  policy      = data.aws_iam_policy_document.elastic_ip_manager.json
}

resource "aws_iam_role" "elastic_ip_manager" {
  name               = var.name
  description        = "The role which can be assumed by elastic-ip-manager lambda function"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "elastic_ip_manager" {
  role       = aws_iam_role.elastic_ip_manager.name
  policy_arn = aws_iam_policy.elastic_ip_manager.arn
}

resource "aws_iam_role_policy_attachment" "lambda" {
  role       = aws_iam_role.elastic_ip_manager.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ---------------------------------------------------------------------------------------------------------------------
# AWS Lambda Function
# ---------------------------------------------------------------------------------------------------------------------

resource "aws_lambda_function" "elastic_ip_manager" {
  function_name = var.name
  description   = "ElasticIP manager for Auto Scaling Group instances"
  role          = aws_iam_role.elastic_ip_manager.arn

  s3_bucket = local.s3_bucket
  s3_key    = var.s3_key

  handler = "elastic_ip_manager.handler"
  runtime = "python3.7"
  timeout = 600

  tags = var.tags
}

resource "aws_lambda_permission" "allow_cloudwatch_events" {
  statement_id  = "AllowExecutionFromCloudWatchEvents"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.elastic_ip_manager.function_name
  principal     = "events.amazonaws.com"
}

# ---------------------------------------------------------------------------------------------------------------------
# AWS CloudWatch Event Rules to trigger Lambda Function
# ---------------------------------------------------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "periodic_sync" {
  name                = "${var.name}-periodic-sync"
  description         = "Run a periodic elastic-ip-manager sync"
  schedule_expression = "rate(5 minutes)"

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "periodic_sync" {
  target_id = "${var.name}-periodic-sync"
  rule      = aws_cloudwatch_event_rule.periodic_sync.name
  arn       = aws_lambda_function.elastic_ip_manager.arn
}

resource "aws_cloudwatch_event_rule" "triggered_sync" {
  name        = "${var.name}-triggered-sync"
  description = "Run a elastic-ip-manager sync triggered by the event"

  event_pattern = <<-EOS
    {
      "source": [
        "aws.ec2"
      ],
      "detail-type": [
        "EC2 Instance State-change Notification"
      ]
    }
    EOS

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "triggered_sync" {
  target_id = "${var.name}-triggered-sync"
  rule      = aws_cloudwatch_event_rule.triggered_sync.name
  arn       = aws_lambda_function.elastic_ip_manager.arn
}
