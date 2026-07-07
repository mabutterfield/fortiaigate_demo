data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

data "terraform_remote_state" "aws_ecr" {
  count   = var.registry_backend == "ecr" ? 1 : 0
  backend = "local"

  config = {
    path = var.aws_ecr_state_path
  }
}

resource "time_offset" "bedrock_expiration" {
  count = var.enable_bedrock_iam ? 1 : 0

  offset_days = var.bedrock_credential_valid_days

  triggers = {
    generation = var.bedrock_credential_generation
  }
}

locals {
  ec2_iam_role_name         = var.ec2_iam_role_name != "" ? var.ec2_iam_role_name : "${var.name_prefix}-ec2-role"
  ec2_instance_profile_name = var.ec2_instance_profile_name != "" ? var.ec2_instance_profile_name : "${var.name_prefix}-ec2-profile"
  bedrock_user_name         = "${var.name_prefix}-bedrock"
  ecr_repository_arns       = var.registry_backend == "ecr" ? values(data.terraform_remote_state.aws_ecr[0].outputs.repository_arns) : []
  allowed_ingress_cidrs = distinct([
    for cidr in(
      can(tolist(var.allowed_ingress_cidr))
      ? tolist(var.allowed_ingress_cidr)
      : [tostring(var.allowed_ingress_cidr)]
    ) : trimspace(cidr)
    if trimspace(cidr) != ""
  ])

  eip_allocations = {
    for name, enabled in var.allocate_eips : name => enabled
    if enabled
  }

  k3s_public_ip_cidr = try("${aws_eip.public["k3s"].public_ip}/32", "")

  bedrock_effective_allowed_source_cidrs = var.bedrock_no_ip_restriction ? [] : distinct(compact(concat(
    local.allowed_ingress_cidrs,
    [
      local.k3s_public_ip_cidr,
    ],
    var.bedrock_allowed_source_cidrs
  )))

  bedrock_foundation_model_arns = flatten([
    for region in var.bedrock_allowed_regions : [
      for model_id in var.bedrock_model_ids :
      "arn:${data.aws_partition.current.partition}:bedrock:${region}::foundation-model/${model_id}*"
    ]
  ])

  bedrock_expiration_deny_statements = var.enable_bedrock_iam ? [
    {
      Sid      = "DenyAfterExpiration"
      Effect   = "Deny"
      Action   = "*"
      Resource = "*"
      Condition = {
        DateGreaterThan = {
          "aws:CurrentTime" = time_offset.bedrock_expiration[0].rfc3339
        }
      }
    }
  ] : []

  bedrock_source_ip_deny_statements = var.enable_bedrock_iam && length(local.bedrock_effective_allowed_source_cidrs) > 0 ? [
    {
      Sid      = "DenyOutsideAllowedSourceIps"
      Effect   = "Deny"
      Action   = "*"
      Resource = "*"
      Condition = {
        NotIpAddress = {
          "aws:SourceIp" = local.bedrock_effective_allowed_source_cidrs
        }
      }
    }
  ] : []

  bedrock_invoke_allow_statements = [
    {
      Sid    = "AllowBedrockInvoke"
      Effect = "Allow"
      Action = [
        "bedrock:Converse",
        "bedrock:ConverseStream",
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
      ]
      Resource = local.bedrock_foundation_model_arns
    }
  ]

  bedrock_allow_statements = var.enable_bedrock_iam ? local.bedrock_invoke_allow_statements : []

  tags = merge(
    {
      Project = "FortiAIGate Demo"
      Managed = "terraform"
    },
    var.tags
  )
}

resource "aws_iam_role" "ec2" {
  name = local.ec2_iam_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Ec2AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      },
    ]
  })

  tags = merge(local.tags, {
    Name = local.ec2_iam_role_name
  })
}

resource "aws_iam_role_policy_attachment" "ec2_managed" {
  for_each = toset(var.ec2_iam_role_managed_policy_arns)

  role       = aws_iam_role.ec2.name
  policy_arn = each.value
}

resource "aws_iam_instance_profile" "ec2" {
  name = local.ec2_instance_profile_name
  role = aws_iam_role.ec2.name

  tags = merge(local.tags, {
    Name = local.ec2_instance_profile_name
  })
}

resource "aws_iam_policy" "ec2_ecr_pull" {
  count = var.registry_backend == "ecr" ? 1 : 0

  name        = "${var.name_prefix}-ec2-ecr-pull"
  description = "Allow the FortiAIGate k3s host to pull release images from private ECR."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EcrAuthToken"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
        ]
        Resource = "*"
      },
      {
        Sid    = "EcrPullFortiAIGateImages"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:DescribeImages",
          "ecr:DescribeRepositories",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = local.ecr_repository_arns
      },
    ]
  })

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-ec2-ecr-pull"
  })
}

resource "aws_iam_role_policy_attachment" "ec2_ecr_pull" {
  count = var.registry_backend == "ecr" ? 1 : 0

  role       = aws_iam_role.ec2.name
  policy_arn = aws_iam_policy.ec2_ecr_pull[0].arn
}

resource "aws_iam_policy" "ec2_bedrock_invoke" {
  count = var.enable_ec2_bedrock_iam ? 1 : 0

  name        = "${var.name_prefix}-ec2-bedrock-invoke"
  description = "Allow the FortiAIGate k3s host to invoke selected Bedrock models."

  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = local.bedrock_invoke_allow_statements
  })

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-ec2-bedrock-invoke"
  })
}

resource "aws_iam_role_policy_attachment" "ec2_bedrock_invoke" {
  count = var.enable_ec2_bedrock_iam ? 1 : 0

  role       = aws_iam_role.ec2.name
  policy_arn = aws_iam_policy.ec2_bedrock_invoke[0].arn
}

resource "aws_eip" "public" {
  for_each = local.eip_allocations

  domain = "vpc"

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-${each.key}-eip"
  })
}

resource "aws_iam_user" "bedrock" {
  count = var.enable_bedrock_iam ? 1 : 0

  name = local.bedrock_user_name
  tags = merge(local.tags, {
    Component = "Bedrock"
    Purpose   = "Bedrock lab access"
    ExpiresAt = time_offset.bedrock_expiration[0].rfc3339
  })
}

resource "aws_iam_access_key" "bedrock" {
  count = var.enable_bedrock_iam ? 1 : 0

  user = aws_iam_user.bedrock[0].name
}

resource "aws_iam_user_policy" "bedrock" {
  count = var.enable_bedrock_iam ? 1 : 0

  name = "${var.name_prefix}-bedrock-invoke"
  user = aws_iam_user.bedrock[0].name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      local.bedrock_expiration_deny_statements,
      local.bedrock_source_ip_deny_statements,
      local.bedrock_allow_statements
    )
  })
}
