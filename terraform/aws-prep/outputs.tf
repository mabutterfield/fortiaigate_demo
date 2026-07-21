output "aws_account_id" {
  description = "AWS account ID used for prep resources."
  value       = data.aws_caller_identity.current.account_id
}

output "aws_profile" {
  description = "AWS CLI profile used by this Terraform module."
  value       = var.aws_profile
}

output "aws_region" {
  description = "AWS region used by this Terraform module."
  value       = var.aws_region
}

output "allowed_ingress_cidr" {
  description = "First trusted source CIDR used by the lab. Kept for compatibility with older references."
  value       = local.allowed_ingress_cidrs[0]
}

output "allowed_ingress_cidrs" {
  description = "Trusted source CIDRs used by the lab."
  value       = local.allowed_ingress_cidrs
}

output "ec2_iam_role_name" {
  description = "IAM role name for the k3s EC2 host."
  value       = aws_iam_role.ec2.name
}

output "ec2_instance_profile_name" {
  description = "IAM instance profile name for the k3s EC2 host."
  value       = aws_iam_instance_profile.ec2.name
}

# Outputs above and k3s_eip_allocation_id below are consumed by
# terraform/aws-ec2-k3s. Keep them even though they are less user-facing than
# public IPs, Bedrock models, and credential metadata.

# These policy/repository ARN outputs are excess for normal operators. They are
# easy to add back when debugging IAM policy scope or repository attachment.
# output "ecr_pull_policy_arn" {
#   description = "Scoped ECR pull policy attached to the EC2 role when registry_backend is ecr."
#   value       = var.registry_backend == "ecr" ? aws_iam_policy.ec2_ecr_pull[0].arn : null
# }
#
# output "ec2_bedrock_invoke_policy_arn" {
#   description = "Scoped Bedrock invoke policy attached to the EC2 role when enable_ec2_bedrock_iam is true."
#   value       = var.enable_ec2_bedrock_iam ? aws_iam_policy.ec2_bedrock_invoke[0].arn : null
# }
#
# output "ecr_pull_repository_arns" {
#   description = "ECR repository ARNs included in the EC2 pull policy."
#   value       = local.ecr_repository_arns
# }

output "k3s_eip_allocation_id" {
  description = "Preallocated EIP allocation ID for the k3s host."
  value       = try(aws_eip.public["k3s"].id, null)
}

output "k3s_public_ip" {
  description = "Preallocated public IP for the k3s host."
  value       = try(aws_eip.public["k3s"].public_ip, null)
}

output "fortigate_eip_allocation_id" {
  description = "Preallocated EIP allocation ID for FortiGate."
  value       = try(aws_eip.public["fortigate"].id, null)
}

output "fortigate_public_ip" {
  description = "Preallocated public IP for FortiGate."
  value       = try(aws_eip.public["fortigate"].public_ip, null)
}

output "fortigate_eip_public_ip" {
  description = "Preallocated EIP public IP for FortiGate. Kept explicit for appliance modules and operator checks."
  value       = try(aws_eip.public["fortigate"].public_ip, null)
}

output "fortiweb_eip_allocation_id" {
  description = "Preallocated EIP allocation ID for FortiWeb."
  value       = try(aws_eip.public["fortiweb"].id, null)
}

output "fortiweb_public_ip" {
  description = "Preallocated public IP for FortiWeb."
  value       = try(aws_eip.public["fortiweb"].public_ip, null)
}

output "fortiweb_eip_public_ip" {
  description = "Preallocated EIP public IP for FortiWeb. Kept explicit for appliance modules and operator checks."
  value       = try(aws_eip.public["fortiweb"].public_ip, null)
}

output "fortiweb_cloudinit_bucket_name" {
  description = "S3 bucket for FortiWeb cloud-init config and license objects."
  value       = var.fortiweb_enabled ? aws_s3_bucket.fortiweb_cloudinit[0].bucket : null
}

output "fortiweb_cloudinit_bucket_arn" {
  description = "S3 bucket ARN for FortiWeb cloud-init config and license objects."
  value       = var.fortiweb_enabled ? aws_s3_bucket.fortiweb_cloudinit[0].arn : null
}

output "fortiweb_cloudinit_config_key" {
  description = "Default S3 object key for the FortiWeb command/config file."
  value       = var.fortiweb_enabled ? var.fortiweb_cloudinit_config_key : null
}

output "fortiweb_cloudinit_license_key" {
  description = "Default S3 object key for the FortiWeb BYOL license file."
  value       = var.fortiweb_enabled ? var.fortiweb_cloudinit_license_key : null
}

output "fortiweb_cloudinit_instance_profile_name" {
  description = "IAM instance profile FortiWeb should use to read S3 cloud-init objects."
  value       = var.fortiweb_enabled ? aws_iam_instance_profile.fortiweb_cloudinit[0].name : null
}

output "fortiweb_cloudinit_role_arn" {
  description = "IAM role ARN FortiWeb uses to read S3 cloud-init objects."
  value       = var.fortiweb_enabled ? aws_iam_role.fortiweb_cloudinit[0].arn : null
}

output "phase8_documents_bucket_name" {
  description = "Optional private S3 bucket for pre-staged synthetic Phase 8 document fixtures."
  value       = var.phase8_documents_bucket_enabled ? aws_s3_bucket.phase8_documents[0].bucket : null
}

output "phase8_documents_bucket_arn" {
  description = "Optional private S3 bucket ARN for pre-staged synthetic Phase 8 document fixtures."
  value       = var.phase8_documents_bucket_enabled ? aws_s3_bucket.phase8_documents[0].arn : null
}

output "phase8_documents_prefix" {
  description = "Allow-listed S3 prefix for synthetic Phase 8 document fixtures."
  value       = var.phase8_documents_bucket_enabled ? local.phase8_documents_prefix : null
}

output "phase8_documents_ec2_read_policy_arn" {
  description = "Optional IAM policy ARN attached to the k3s EC2 role for read-only Phase 8 document fixture access."
  value       = var.phase8_documents_bucket_enabled ? aws_iam_policy.ec2_phase8_documents_read[0].arn : null
}

output "fortiaigate_syslog_bucket_name" {
  description = "Optional private S3 bucket for FortiAIGate syslog preservation."
  value       = var.fortiaigate_syslog_bucket_enabled ? aws_s3_bucket.fortiaigate_syslog[0].bucket : null
}

output "fortiaigate_syslog_bucket_arn" {
  description = "Optional private S3 bucket ARN for FortiAIGate syslog preservation."
  value       = var.fortiaigate_syslog_bucket_enabled ? aws_s3_bucket.fortiaigate_syslog[0].arn : null
}

output "fortiaigate_syslog_prefix" {
  description = "S3 prefix where the FortiAIGate syslog collector writes logs."
  value       = var.fortiaigate_syslog_bucket_enabled ? local.fortiaigate_syslog_prefix : null
}

output "fortiaigate_syslog_ec2_write_policy_arn" {
  description = "Optional IAM policy ARN attached to the k3s EC2 role for FortiAIGate syslog S3 writes."
  value       = var.fortiaigate_syslog_bucket_enabled ? aws_iam_policy.ec2_fortiaigate_syslog_write[0].arn : null
}

output "bedrock_iam_user_name" {
  description = "IAM user created for FortiAIGate Bedrock integration."
  value       = var.enable_bedrock_iam ? aws_iam_user.bedrock[0].name : null
}

output "bedrock_access_key_id" {
  description = "Access Key ID for FortiAIGate Bedrock integration."
  value       = var.enable_bedrock_iam ? aws_iam_access_key.bedrock[0].id : null
}

output "bedrock_secret_access_key" {
  description = "Secret Access Key for FortiAIGate Bedrock integration."
  value       = var.enable_bedrock_iam ? aws_iam_access_key.bedrock[0].secret : null
  sensitive   = true
}

output "bedrock_key_expires_at" {
  description = "Timestamp after which the Bedrock IAM policy denies all access."
  value       = var.enable_bedrock_iam ? time_offset.bedrock_expiration[0].rfc3339 : null
}

output "bedrock_allowed_regions" {
  description = "AWS regions where the Bedrock access key can invoke selected models."
  value       = var.bedrock_allowed_regions
}

output "bedrock_region" {
  description = "Default AWS region for Bedrock tests."
  value       = var.aws_region
}

output "bedrock_model_ids" {
  description = "Allowed Bedrock model IDs."
  value       = var.bedrock_model_ids
}

# The expanded model ARNs are excess for normal operators. The model IDs above
# are the values users need for FortiAIGate/OpenWebUI setup, and this is easy to
# add back when debugging IAM resource scope.
# output "bedrock_model_resource_arns" {
#   description = "Foundation model ARNs allowed by the Bedrock access key policy."
#   value       = local.bedrock_foundation_model_arns
# }

output "bedrock_allowed_source_cidrs" {
  description = "Effective public source CIDRs allowed to use the Bedrock access key."
  value       = local.bedrock_effective_allowed_source_cidrs
}

output "bedrock_source_ip_restriction_enabled" {
  description = "Whether the Bedrock access key policy includes a source IP deny."
  value       = var.enable_bedrock_iam && !var.bedrock_no_ip_restriction && length(local.bedrock_effective_allowed_source_cidrs) > 0
}
