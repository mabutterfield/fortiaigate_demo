data "aws_caller_identity" "current" {}

locals {
  ecr_registry = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"

  common_tags = merge(
    {
      Project   = "FortiAIGate"
      Component = "ECR"
      Managed   = "terraform"
    },
    var.tags
  )

  repository_names = {
    for repository in var.repositories : repository => "${var.repo_prefix}/${repository}"
  }
}

resource "aws_ecr_repository" "this" {
  for_each = local.repository_names

  name                 = each.value
  image_tag_mutability = lookup(var.image_tag_mutability_overrides, each.key, var.image_tag_mutability)

  encryption_configuration {
    encryption_type = "AES256"
  }

  image_scanning_configuration {
    scan_on_push = var.scan_on_push
  }

  tags = local.common_tags
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Retain the most recent tagged FortiAIGate images"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["*"]
          countType      = "imageCountMoreThan"
          countNumber    = var.lifecycle_retain_tagged_count
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = {
          type = "expire"
        }
      },
    ]
  })
}

resource "local_file" "ansible_ecr_vars" {
  filename        = var.ansible_ecr_vars_output_path
  file_permission = "0644"

  content = yamlencode({
    aws_profile                  = var.aws_profile
    aws_region                   = var.aws_region
    aws_account_id               = data.aws_caller_identity.current.account_id
    ecr_account_id               = data.aws_caller_identity.current.account_id
    ecr_registry                 = local.ecr_registry
    ecr_repo_prefix              = var.repo_prefix
    registry_type                = "ecr"
    registry                     = local.ecr_registry
    repo_prefix                  = var.repo_prefix
    fortiaigate_image_repository = "${local.ecr_registry}/${var.repo_prefix}"
    ecr_repository_urls = {
      for name, repository in aws_ecr_repository.this : name => repository.repository_url
    }
  })
}
