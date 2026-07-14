variable "aws_profile" {
  type        = string
  description = "AWS CLI SSO profile name."
}

variable "aws_region" {
  type        = string
  description = "AWS region for private ECR repositories."
  default     = "us-east-1"
}

variable "name_prefix" {
  type        = string
  description = "Shared name prefix from terraform/common.tfvars. Accepted for common config consistency; ECR uses repo_prefix for repository names."
}

variable "allowed_ingress_cidr" {
  type        = any
  description = "Shared trusted source CIDR or list of CIDRs from terraform/common.tfvars. Accepted for common config consistency; not used by ECR."
}

variable "repo_prefix" {
  type        = string
  description = "Repository namespace prefix."
  default     = "fortiaigate"
}

variable "repositories" {
  type        = set(string)
  description = "FortiAIGate image repository names created under repo_prefix."
  default = [
    "api",
    "core",
    "webui",
    "scanner",
    "logd",
    "license_manager",
    "triton-models",
    "custom-triton",
    "chatbot-basic",
  ]
}

variable "image_tag_mutability" {
  type        = string
  description = "ECR image tag mutability. Use IMMUTABLE for release safety."
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be MUTABLE or IMMUTABLE."
  }
}

variable "image_tag_mutability_overrides" {
  type        = map(string)
  description = "Optional per-repository image tag mutability overrides. Keys match entries in repositories."
  default     = {}

  validation {
    condition     = alltrue([for mutability in values(var.image_tag_mutability_overrides) : contains(["MUTABLE", "IMMUTABLE"], mutability)])
    error_message = "image_tag_mutability_overrides values must be MUTABLE or IMMUTABLE."
  }
}

variable "scan_on_push" {
  type        = bool
  description = "Enable basic ECR scan-on-push."
  default     = true
}

variable "lifecycle_retain_tagged_count" {
  type        = number
  description = "Number of tagged images to retain per repository."
  default     = 10

  validation {
    condition     = var.lifecycle_retain_tagged_count > 0
    error_message = "lifecycle_retain_tagged_count must be greater than zero."
  }
}

variable "ansible_ecr_vars_output_path" {
  type        = string
  description = "Path for generated Ansible ECR vars, relative to this Terraform module."
  default     = "../../ansible/group_vars/ecr.generated.yml"
}

variable "tags" {
  type        = map(string)
  description = "Additional tags for ECR resources."
  default     = {}
}
