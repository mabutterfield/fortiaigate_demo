output "account_id" {
  description = "AWS account ID that owns the private ECR repositories."
  value       = data.aws_caller_identity.current.account_id
}

output "registry" {
  description = "Private ECR registry hostname."
  value       = local.ecr_registry
}

output "repository_urls" {
  description = "Map of logical repository names to private ECR repository URLs."
  value = {
    for name, repository in aws_ecr_repository.this : name => repository.repository_url
  }
}

output "repository_arns" {
  description = "Map of logical repository names to private ECR repository ARNs."
  value = {
    for name, repository in aws_ecr_repository.this : name => repository.arn
  }
}

output "ansible_ecr_vars" {
  description = "Generated Ansible ECR vars path."
  value       = local_file.ansible_ecr_vars.filename
}
