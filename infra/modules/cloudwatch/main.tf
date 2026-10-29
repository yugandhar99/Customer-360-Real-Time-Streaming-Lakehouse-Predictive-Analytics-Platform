variable "aws_region" {
  type    = string
  default = "us-east-1"
}
variable "name_prefix" { type = string }
variable "environment" { type = string }
variable "log_retention_days" { type = number }
variable "firehose_stream_name" { type = string }
variable "freshness_threshold_seconds" { type = number }
variable "budget_email" { type = string }
variable "monthly_budget_usd" { type = number }
variable "tags" { type = map(string) }

resource "aws_cloudwatch_log_group" "application" {
  name              = "/customer360/${var.environment}/application"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "firehose" {
  name              = "/customer360/${var.environment}/firehose"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "athena" {
  name              = "/customer360/${var.environment}/athena"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_metric_filter" "ingestion_failure" {
  name           = "${var.name_prefix}-ingestion-failure"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "{ $.component = \"FirehosePublisher\" && $.severity = \"ERROR\" }"

  metric_transformation {
    name      = "IngestionFailures"
    namespace = "Customer360/${var.environment}"
    value     = "1"
  }
}

resource "aws_cloudwatch_log_metric_filter" "query_failure" {
  name           = "${var.name_prefix}-query-failure"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "{ $.component = \"AthenaBackend\" && $.severity = \"ERROR\" }"

  metric_transformation {
    name      = "QueryFailures"
    namespace = "Customer360/${var.environment}"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "ingestion_failure" {
  alarm_name          = "${var.name_prefix}-ingestion-failure"
  alarm_description   = "A Firehose publish failed after retries. Threshold is one error in five minutes because the publisher already retried the same event."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "IngestionFailures"
  namespace           = "Customer360/${var.environment}"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "query_failure" {
  alarm_name          = "${var.name_prefix}-query-failure"
  alarm_description   = "An Athena query failed. Missing data does not alarm, so an idle development environment stays quiet."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "QueryFailures"
  namespace           = "Customer360/${var.environment}"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "freshness" {
  alarm_name          = "${var.name_prefix}-firehose-freshness"
  alarm_description   = "S3 delivery freshness exceeded 900 seconds. Normal buffering is 60 seconds, so this threshold means delivery is stuck."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "DeliveryToS3.DataFreshness"
  namespace           = "AWS/Firehose"
  period              = 300
  statistic           = "Maximum"
  threshold           = var.freshness_threshold_seconds
  treat_missing_data  = "notBreaching"
  dimensions = {
    DeliveryStreamName = var.firehose_stream_name
  }
  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "delivery_success" {
  alarm_name          = "${var.name_prefix}-firehose-delivery-success"
  alarm_description   = "Firehose reported unsuccessful S3 delivery. Missing data is not a breach because an idle stream has no delivery attempts."
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "DeliveryToS3.Success"
  namespace           = "AWS/Firehose"
  period              = 300
  statistic           = "Average"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  dimensions = {
    DeliveryStreamName = var.firehose_stream_name
  }
  tags = var.tags
}

resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = "${var.name_prefix}-operations"
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Firehose delivery freshness"
          region = var.aws_region
          metrics = [
            ["AWS/Firehose", "DeliveryToS3.DataFreshness", "DeliveryStreamName", var.firehose_stream_name],
          ]
          period = 300
          stat   = "Maximum"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Application failures"
          region = var.aws_region
          metrics = [
            ["Customer360/${var.environment}", "IngestionFailures"],
            ["Customer360/${var.environment}", "QueryFailures"],
          ]
          period = 300
          stat   = "Sum"
        }
      }
    ]
  })
}

resource "aws_budgets_budget" "monthly" {
  count        = var.budget_email == "" ? 0 : 1
  name         = "${var.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_email]
  }
}

output "application_log_group_name" {
  value = aws_cloudwatch_log_group.application.name
}

output "firehose_log_group_name" {
  value = aws_cloudwatch_log_group.firehose.name
}

output "firehose_log_group_arn" {
  value = aws_cloudwatch_log_group.firehose.arn
}
