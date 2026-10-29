variable "name_prefix" { type = string }
variable "aws_region" { type = string }
variable "bucket_arn" { type = string }
variable "firehose_stream_name" { type = string }
variable "firehose_log_group_arn" { type = string }
variable "glue_database_name" { type = string }
variable "athena_workgroup_name" { type = string }
variable "ecr_repository_arn" { type = string }
variable "github_repository" { type = string }
variable "enable_eks" { type = bool }
variable "eks_cluster_name" { type = string }
variable "tags" { type = map(string) }

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
}

data "aws_iam_policy_document" "firehose_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["firehose.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "firehose" {
  name               = "${var.name_prefix}-firehose"
  assume_role_policy = data.aws_iam_policy_document.firehose_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "firehose" {
  statement {
    sid = "WriteRawEvents"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:GetBucketLocation",
      "s3:GetObject",
      "s3:ListBucket",
      "s3:PutObject",
    ]
    resources = [
      var.bucket_arn,
      "${var.bucket_arn}/raw/*",
    ]
  }

  statement {
    sid = "WriteDeliveryLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      var.firehose_log_group_arn,
      "${var.firehose_log_group_arn}:*",
    ]
  }
}

resource "aws_iam_role_policy" "firehose" {
  name   = "firehose-delivery"
  role   = aws_iam_role.firehose.id
  policy = data.aws_iam_policy_document.firehose.json
}

data "aws_iam_policy_document" "analytics" {
  statement {
    sid = "PublishEventsToFirehose"
    actions = [
      "firehose:PutRecord",
      "firehose:PutRecordBatch",
      "firehose:DescribeDeliveryStream",
    ]
    resources = [
      "arn:${local.partition}:firehose:${var.aws_region}:${local.account_id}:deliverystream/${var.firehose_stream_name}",
    ]
  }

  statement {
    sid = "AthenaQueries"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:StopQueryExecution",
      "athena:GetWorkGroup",
    ]
    resources = [
      "arn:${local.partition}:athena:${var.aws_region}:${local.account_id}:workgroup/${var.athena_workgroup_name}",
    ]
  }

  statement {
    sid = "GlueCatalogRead"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetPartition",
      "glue:GetPartitions",
    ]
    resources = [
      "arn:${local.partition}:glue:${var.aws_region}:${local.account_id}:catalog",
      "arn:${local.partition}:glue:${var.aws_region}:${local.account_id}:database/${var.glue_database_name}",
      "arn:${local.partition}:glue:${var.aws_region}:${local.account_id}:table/${var.glue_database_name}/*",
    ]
  }

  statement {
    sid       = "ListAnalyticsPrefixes"
    actions   = ["s3:ListBucket"]
    resources = [var.bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*", "analytics/*", "athena-results/*", "test-fixtures/*"]
    }
  }

  statement {
    sid = "ReadEventsAndMetrics"
    actions = [
      "s3:GetObject",
    ]
    resources = [
      "${var.bucket_arn}/raw/*",
      "${var.bucket_arn}/analytics/*",
      "${var.bucket_arn}/test-fixtures/*",
    ]
  }

  statement {
    sid = "WriteQueryOutputAndMetrics"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = [
      "${var.bucket_arn}/analytics/*",
      "${var.bucket_arn}/athena-results/*",
    ]
  }
}

resource "aws_iam_policy" "analytics" {
  name   = "${var.name_prefix}-analytics"
  policy = data.aws_iam_policy_document.analytics.json
  tags   = var.tags
}

data "aws_iam_policy_document" "eks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eks_cluster" {
  count              = var.enable_eks ? 1 : 0
  name               = "${var.name_prefix}-eks-cluster"
  assume_role_policy = data.aws_iam_policy_document.eks_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "eks_cluster" {
  count      = var.enable_eks ? 1 : 0
  role       = aws_iam_role.eks_cluster[0].name
  policy_arn = "arn:${local.partition}:iam::aws:policy/AmazonEKSClusterPolicy"
}

data "aws_iam_policy_document" "node_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eks_node" {
  count              = var.enable_eks ? 1 : 0
  name               = "${var.name_prefix}-eks-node"
  assume_role_policy = data.aws_iam_policy_document.node_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "eks_node" {
  for_each = var.enable_eks ? toset([
    "arn:${local.partition}:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:${local.partition}:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:${local.partition}:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
  ]) : toset([])
  role       = aws_iam_role.eks_node[0].name
  policy_arn = each.value
}

resource "aws_iam_openid_connect_provider" "github" {
  count           = var.github_repository == "" ? 0 : 1
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
  tags            = var.tags
}

data "aws_iam_policy_document" "github_assume" {
  count = var.github_repository == "" ? 0 : 1
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github" {
  count              = var.github_repository == "" ? 0 : 1
  name               = "${var.name_prefix}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume[0].json
  tags               = var.tags
}

data "aws_iam_policy_document" "github" {
  count = var.github_repository == "" ? 0 : 1
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeRepositories",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [var.ecr_repository_arn]
  }

  statement {
    sid       = "DescribeCluster"
    actions   = ["eks:DescribeCluster"]
    resources = ["arn:${local.partition}:eks:${var.aws_region}:${local.account_id}:cluster/${var.eks_cluster_name}"]
  }
}

resource "aws_iam_role_policy" "github" {
  count  = var.github_repository == "" ? 0 : 1
  name   = "deploy"
  role   = aws_iam_role.github[0].id
  policy = data.aws_iam_policy_document.github[0].json
}

output "firehose_role_arn" {
  value = aws_iam_role.firehose.arn
}

output "analytics_policy_arn" {
  value = aws_iam_policy.analytics.arn
}

output "eks_cluster_role_arn" {
  value = try(aws_iam_role.eks_cluster[0].arn, "")
}

output "eks_node_role_arn" {
  value = try(aws_iam_role.eks_node[0].arn, "")
}

output "github_role_arn" {
  value = try(aws_iam_role.github[0].arn, "")
}
