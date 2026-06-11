output "account_id" {
  description = "AWS account ID used for Bedrock credential setup."
  value       = data.aws_caller_identity.current.account_id
}

output "bedrock_iam_user_name" {
  description = "IAM user created for FortiAIGate Bedrock integration."
  value       = aws_iam_user.bedrock.name
}

output "bedrock_access_key_id" {
  description = "Access Key ID for FortiAIGate Bedrock integration."
  value       = aws_iam_access_key.bedrock.id
}

output "bedrock_secret_access_key" {
  description = "Secret Access Key for FortiAIGate Bedrock integration."
  value       = aws_iam_access_key.bedrock.secret
  sensitive   = true
}

output "bedrock_key_expires_at" {
  description = "Timestamp after which the IAM policy denies all access."
  value       = time_offset.bedrock_expiration.rfc3339
}

output "bedrock_region" {
  description = "AWS region for Bedrock."
  value       = var.aws_region
}

output "bedrock_allowed_regions" {
  description = "AWS regions where the Bedrock access key can invoke selected models."
  value       = var.bedrock_allowed_regions
}

output "bedrock_model_ids" {
  description = "Allowed Bedrock model IDs."
  value       = var.bedrock_model_ids
}

output "bedrock_model_resource_arns" {
  description = "Foundation model ARNs allowed by the Bedrock access key policy."
  value       = local.foundation_model_arns
}

output "bedrock_allowed_source_cidrs" {
  description = "Effective public source CIDRs allowed to use the Bedrock access key."
  value       = local.effective_allowed_source_cidrs
}

output "bedrock_source_ip_restriction_enabled" {
  description = "Whether the Bedrock access key policy includes a source IP deny."
  value       = !var.no_ip_restriction && length(local.effective_allowed_source_cidrs) > 0
}
