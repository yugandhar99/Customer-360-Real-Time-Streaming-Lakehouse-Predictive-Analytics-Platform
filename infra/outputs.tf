output "s3_bucket_name" {
  description = "Event and analytics bucket. Use this as AWS_S3_BUCKET."
  value       = module.s3.bucket_name
}

output "firehose_stream_name" {
  description = "Delivery stream. Use this as AWS_FIREHOSE_STREAM."
  value       = module.firehose.stream_name
}

output "glue_database_name" {
  description = "Glue database. Use this as AWS_GLUE_DATABASE."
  value       = module.glue.database_name
}

output "athena_workgroup_name" {
  description = "Athena workgroup. Use this as ATHENA_WORKGROUP."
  value       = module.athena.workgroup_name
}

output "athena_results_s3_uri" {
  description = "Athena result location. Use this as ATHENA_RESULTS_S3_URI."
  value       = module.athena.results_s3_uri
}

output "ecr_repository_url" {
  description = "Dashboard image repository. Empty while enable_ecr is false."
  value       = module.ecr.repository_url
}

output "analytics_policy_arn" {
  description = "Attach this managed policy to the runtime/deploy identity that publishes events and queries Athena."
  value       = module.iam.analytics_policy_arn
}

output "firehose_role_arn" {
  description = "Service role used by Firehose to write to S3. Terraform passes this role to the delivery stream."
  value       = module.iam.firehose_role_arn
}

output "github_role_arn" {
  description = "OIDC role for the deployment workflow. Null until github_repository is set."
  value       = module.iam.github_role_arn
}

output "analytics_role_arn" {
  description = "IAM role for the dashboard service account. Empty until EKS is enabled."
  value       = module.eks.analytics_role_arn
}

output "eks_cluster_name" {
  description = "EKS cluster name. Null while enable_eks is false."
  value       = module.eks.cluster_name
}

output "application_log_group" {
  description = "CloudWatch log group expected to receive container stdout."
  value       = module.cloudwatch.application_log_group_name
}
