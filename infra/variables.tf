variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used in resource names."
  type        = string
  default     = "customer360"
}

variable "environment" {
  description = "Deployment environment, for example dev or prod."
  type        = string
  default     = "dev"
}

variable "bucket_name" {
  description = "Globally unique S3 bucket for events, analytics output, and Athena results."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name must be a valid lowercase S3 bucket name."
  }
}

variable "raw_retention_days" {
  description = "Days to keep raw Firehose objects and access logs."
  type        = number
  default     = 90
}

variable "athena_results_retention_days" {
  description = "Days to keep Athena query output."
  type        = number
  default     = 7
}

variable "error_retention_days" {
  description = "Days to keep Firehose delivery errors."
  type        = number
  default     = 30
}

variable "force_destroy" {
  description = "Allow Terraform to delete non-empty buckets. Leave false outside disposable development."
  type        = bool
  default     = false
}

variable "glue_database_name" {
  description = "Glue database that matches AWS_GLUE_DATABASE."
  type        = string
  default     = "customer_360"
}

variable "athena_bytes_scanned_cutoff" {
  description = "Per-query Athena scan limit. One GiB keeps a development query from scanning unbounded data."
  type        = number
  default     = 1073741824
}

variable "log_retention_days" {
  description = "CloudWatch log retention. Fourteen days is the development default."
  type        = number
  default     = 14
}

variable "firehose_buffer_interval_seconds" {
  description = "Firehose S3 buffer interval. Sixty seconds is the freshness target for this analytics workload."
  type        = number
  default     = 60
}

variable "firehose_buffer_size_mb" {
  description = "Firehose S3 buffer size in megabytes."
  type        = number
  default     = 1
}

variable "freshness_alarm_seconds" {
  description = "Alarm when Firehose S3 freshness exceeds this many seconds. Nine hundred seconds is fifteen times the 60 second buffer."
  type        = number
  default     = 900
}

variable "enable_vpc" {
  description = "Create a VPC. Enabled automatically when enable_eks is true."
  type        = bool
  default     = false
}

variable "enable_nat_gateway" {
  description = "Create one NAT gateway. Leave false in development; a NAT gateway is about 32 USD per month before data charges."
  type        = bool
  default     = false
}

variable "enable_eks" {
  description = "Create an EKS control plane and one t3.small node. Leave false until deployment is authorized."
  type        = bool
  default     = false
}

variable "enable_ecr" {
  description = "Create an ECR repository for the dashboard image. Leave false for the data-layer-only phase."
  type        = bool
  default     = false
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the deploy role, in org/name form. Empty skips the OIDC role."
  type        = string
  default     = ""
}

variable "budget_email" {
  description = "Email for AWS Budget alerts. Empty skips the budget so no notification target is invented."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget in USD. Notifications are created only when budget_email is set."
  type        = number
  default     = 25
}
