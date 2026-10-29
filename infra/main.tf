locals {
  name_prefix      = "${var.project_name}-${var.environment}"
  log_bucket_name  = "${var.bucket_name}-logs"
  firehose_stream  = "${local.name_prefix}-events"
  athena_workgroup = "${local.name_prefix}-analytics"
  ecr_repository   = "${local.name_prefix}-dashboard"
  create_network   = var.enable_vpc || var.enable_eks
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Application = "customer-360"
  }
}

module "s3" {
  source                        = "./modules/s3"
  bucket_name                   = var.bucket_name
  log_bucket_name               = local.log_bucket_name
  force_destroy                 = var.force_destroy
  raw_retention_days            = var.raw_retention_days
  athena_results_retention_days = var.athena_results_retention_days
  error_retention_days          = var.error_retention_days
  tags                          = local.common_tags
}

module "cloudwatch" {
  source                      = "./modules/cloudwatch"
  aws_region                  = var.aws_region
  name_prefix                 = local.name_prefix
  environment                 = var.environment
  log_retention_days          = var.log_retention_days
  firehose_stream_name        = local.firehose_stream
  freshness_threshold_seconds = var.freshness_alarm_seconds
  budget_email                = var.budget_email
  monthly_budget_usd          = var.monthly_budget_usd
  tags                        = local.common_tags
}

module "ecr" {
  source          = "./modules/ecr"
  enable          = var.enable_ecr
  repository_name = local.ecr_repository
  tags            = local.common_tags
}

module "iam" {
  source                 = "./modules/iam"
  name_prefix            = local.name_prefix
  aws_region             = var.aws_region
  bucket_arn             = module.s3.bucket_arn
  firehose_stream_name   = local.firehose_stream
  firehose_log_group_arn = module.cloudwatch.firehose_log_group_arn
  glue_database_name     = var.glue_database_name
  athena_workgroup_name  = local.athena_workgroup
  ecr_repository_arn     = module.ecr.repository_arn
  github_repository      = var.github_repository
  enable_eks             = var.enable_eks
  eks_cluster_name       = "${local.name_prefix}-eks"
  tags                   = local.common_tags
}

module "firehose" {
  source          = "./modules/firehose"
  stream_name     = local.firehose_stream
  bucket_arn      = module.s3.bucket_arn
  role_arn        = module.iam.firehose_role_arn
  log_group_name  = module.cloudwatch.firehose_log_group_name
  buffer_interval = var.firehose_buffer_interval_seconds
  buffer_size     = var.firehose_buffer_size_mb
  tags            = local.common_tags
}

module "glue" {
  source        = "./modules/glue"
  database_name = var.glue_database_name
  bucket_name   = module.s3.bucket_name
  tags          = local.common_tags
}

module "athena" {
  source               = "./modules/athena"
  workgroup_name       = local.athena_workgroup
  bucket_name          = module.s3.bucket_name
  bytes_scanned_cutoff = var.athena_bytes_scanned_cutoff
  tags                 = local.common_tags
}

module "networking" {
  source             = "./modules/networking"
  enable             = local.create_network
  name_prefix        = local.name_prefix
  aws_region         = var.aws_region
  enable_nat_gateway = var.enable_nat_gateway
  tags               = local.common_tags
}

module "eks" {
  source               = "./modules/eks"
  enable               = var.enable_eks
  name_prefix          = local.name_prefix
  cluster_name         = "${local.name_prefix}-eks"
  cluster_role_arn     = module.iam.eks_cluster_role_arn
  node_role_arn        = module.iam.eks_node_role_arn
  analytics_policy_arn = module.iam.analytics_policy_arn
  subnet_ids           = module.networking.eks_subnet_ids
  github_role_arn      = module.iam.github_role_arn
  tags                 = local.common_tags

  depends_on = [module.iam]
}
