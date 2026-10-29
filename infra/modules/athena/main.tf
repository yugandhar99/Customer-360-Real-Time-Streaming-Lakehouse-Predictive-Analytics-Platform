variable "workgroup_name" { type = string }
variable "bucket_name" { type = string }
variable "bytes_scanned_cutoff" { type = number }
variable "tags" { type = map(string) }

resource "aws_athena_workgroup" "this" {
  name = var.workgroup_name

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.bytes_scanned_cutoff

    result_configuration {
      output_location = "s3://${var.bucket_name}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }

  tags = var.tags
}

output "workgroup_name" {
  value = aws_athena_workgroup.this.name
}

output "results_s3_uri" {
  value = "s3://${var.bucket_name}/athena-results/"
}
