variable "stream_name" { type = string }
variable "bucket_arn" { type = string }
variable "role_arn" { type = string }
variable "log_group_name" { type = string }
variable "buffer_interval" { type = number }
variable "buffer_size" { type = number }
variable "tags" { type = map(string) }

resource "aws_cloudwatch_log_stream" "s3_delivery" {
  name           = "S3Delivery"
  log_group_name = var.log_group_name
}

resource "aws_kinesis_firehose_delivery_stream" "events" {
  name        = var.stream_name
  destination = "extended_s3"

  extended_s3_configuration {
    role_arn            = var.role_arn
    bucket_arn          = var.bucket_arn
    prefix              = "raw/events/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/"
    error_output_prefix = "raw/errors/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/"
    buffering_interval  = var.buffer_interval
    buffering_size      = var.buffer_size
    compression_format  = "GZIP"

    cloudwatch_logging_options {
      enabled         = true
      log_group_name  = var.log_group_name
      log_stream_name = aws_cloudwatch_log_stream.s3_delivery.name
    }
  }

  tags = var.tags
}

output "stream_name" {
  value = aws_kinesis_firehose_delivery_stream.events.name
}

output "stream_arn" {
  value = aws_kinesis_firehose_delivery_stream.events.arn
}
