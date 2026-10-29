variable "enable" { type = bool }
variable "name_prefix" { type = string }
variable "cluster_name" { type = string }
variable "cluster_role_arn" { type = string }
variable "node_role_arn" { type = string }
variable "analytics_policy_arn" { type = string }
variable "subnet_ids" { type = list(string) }
variable "github_role_arn" { type = string }
variable "tags" { type = map(string) }

resource "aws_eks_cluster" "this" {
  count    = var.enable ? 1 : 0
  name     = var.cluster_name
  role_arn = var.cluster_role_arn
  version  = "1.29"

  vpc_config {
    subnet_ids              = var.subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = true
  }

  enabled_cluster_log_types = ["api", "audit", "authenticator"]
  tags                      = var.tags
}

resource "aws_eks_node_group" "this" {
  count           = var.enable ? 1 : 0
  cluster_name    = aws_eks_cluster.this[0].name
  node_group_name = "default"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.subnet_ids
  instance_types  = ["t3.small"]
  capacity_type   = "ON_DEMAND"

  scaling_config {
    desired_size = 1
    min_size     = 1
    max_size     = 2
  }

  tags = var.tags
}

resource "aws_eks_access_entry" "github" {
  count         = var.enable && var.github_role_arn != "" ? 1 : 0
  cluster_name  = aws_eks_cluster.this[0].name
  principal_arn = var.github_role_arn
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "github" {
  count         = var.enable && var.github_role_arn != "" ? 1 : 0
  cluster_name  = aws_eks_cluster.this[0].name
  principal_arn = var.github_role_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"

  access_scope {
    type       = "namespace"
    namespaces = ["customer360"]
  }

  depends_on = [aws_eks_access_entry.github]
}

data "tls_certificate" "oidc" {
  count = var.enable ? 1 : 0
  url   = aws_eks_cluster.this[0].identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  count           = var.enable ? 1 : 0
  url             = aws_eks_cluster.this[0].identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.oidc[0].certificates[0].sha1_fingerprint]
  tags            = var.tags
}

data "aws_iam_policy_document" "analytics_assume" {
  count = var.enable ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.eks[0].arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks[0].url, "https://", "")}:sub"
      values   = ["system:serviceaccount:customer360:customer360-dashboard"]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks[0].url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "analytics" {
  count              = var.enable ? 1 : 0
  name               = "${var.name_prefix}-analytics"
  assume_role_policy = data.aws_iam_policy_document.analytics_assume[0].json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "analytics" {
  count      = var.enable ? 1 : 0
  role       = aws_iam_role.analytics[0].name
  policy_arn = var.analytics_policy_arn
}

output "cluster_name" {
  value = try(aws_eks_cluster.this[0].name, "")
}

output "analytics_role_arn" {
  value = try(aws_iam_role.analytics[0].arn, "")
}
