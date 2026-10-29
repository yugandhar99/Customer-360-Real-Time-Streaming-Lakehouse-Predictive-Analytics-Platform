variable "enable" { type = bool }
variable "repository_name" { type = string }
variable "tags" { type = map(string) }

resource "aws_ecr_repository" "dashboard" {
  count                = var.enable ? 1 : 0
  name                 = var.repository_name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "dashboard" {
  count      = var.enable ? 1 : 0
  repository = aws_ecr_repository.dashboard[0].name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}

output "repository_arn" {
  value = try(aws_ecr_repository.dashboard[0].arn, "")
}

output "repository_url" {
  value = try(aws_ecr_repository.dashboard[0].repository_url, "")
}
