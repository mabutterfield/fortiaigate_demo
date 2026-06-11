data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

data "terraform_remote_state" "ec2_k3s" {
  count   = var.no_ip_restriction ? 0 : 1
  backend = "local"

  config = {
    path = var.ec2_k3s_state_path
  }
}

resource "time_offset" "bedrock_expiration" {
  offset_days = var.credential_valid_days

  triggers = {
    generation = var.credential_generation
  }
}

locals {
  bedrock_user_name = "${var.name_prefix}-bedrock"

  foundation_model_arns = flatten([
    for region in var.bedrock_allowed_regions : [
      for model_id in var.bedrock_model_ids :
      "arn:${data.aws_partition.current.partition}:bedrock:${region}::foundation-model/${model_id}*"
    ]
  ])

  ec2_public_ip_cidr       = try("${data.terraform_remote_state.ec2_k3s[0].outputs.public_ip}/32", "")
  ec2_allowed_ingress_cidr = try(data.terraform_remote_state.ec2_k3s[0].outputs.allowed_ingress_cidr, "")

  effective_allowed_source_cidrs = var.no_ip_restriction ? [] : distinct(compact(concat(
    [
      local.ec2_public_ip_cidr,
      local.ec2_allowed_ingress_cidr,
    ],
    var.allowed_source_cidrs
  )))

  expiration_deny_statements = [
    {
      Sid      = "DenyAfterExpiration"
      Effect   = "Deny"
      Action   = "*"
      Resource = "*"
      Condition = {
        DateGreaterThan = {
          "aws:CurrentTime" = time_offset.bedrock_expiration.rfc3339
        }
      }
    }
  ]

  source_ip_deny_statements = length(local.effective_allowed_source_cidrs) == 0 ? [] : [
    {
      Sid      = "DenyOutsideAllowedSourceIps"
      Effect   = "Deny"
      Action   = "*"
      Resource = "*"
      Condition = {
        NotIpAddress = {
          "aws:SourceIp" = local.effective_allowed_source_cidrs
        }
      }
    }
  ]

  bedrock_allow_statements = [
    {
      Sid    = "AllowBedrockInvoke"
      Effect = "Allow"
      Action = [
        "bedrock:Converse",
        "bedrock:ConverseStream",
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
      ]
      Resource = local.foundation_model_arns
    }
  ]

  common_tags = merge(
    {
      Project   = "FortiAIGate"
      Component = "Bedrock"
      Managed   = "terraform"
      Purpose   = "Bedrock lab access"
      ExpiresAt = time_offset.bedrock_expiration.rfc3339
    },
    var.tags
  )
}

resource "aws_iam_user" "bedrock" {
  name = local.bedrock_user_name
  tags = local.common_tags
}

resource "aws_iam_access_key" "bedrock" {
  user = aws_iam_user.bedrock.name
}

resource "aws_iam_user_policy" "bedrock" {
  name = "${var.name_prefix}-bedrock-invoke"
  user = aws_iam_user.bedrock.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      local.expiration_deny_statements,
      local.source_ip_deny_statements,
      local.bedrock_allow_statements
    )
  })
}
