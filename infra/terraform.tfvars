# Local deploy intent for account 783764597826 / us-east-1.
# Gitignored. Do not apply until cost approval is given in chat.
# Identity must be customer360-deployer (or another approved role).

aws_region   = "us-east-1"
project_name = "customer360"
environment  = "dev"

# Globally unique bucket for this account. Change only if this name is taken.
bucket_name = "customer360-783764597826-dev-data"

raw_retention_days            = 90
athena_results_retention_days = 7
error_retention_days          = 30
force_destroy                 = false

glue_database_name          = "customer_360"
athena_bytes_scanned_cutoff = 1073741824
log_retention_days          = 14

firehose_buffer_interval_seconds = 60
firehose_buffer_size_mb          = 1
freshness_alarm_seconds          = 900

enable_vpc         = false
enable_nat_gateway = false
enable_eks         = false
enable_ecr         = false

github_repository = ""

# Set your alert email before apply if you want a $25 budget notification.
budget_email       = ""
monthly_budget_usd = 25
