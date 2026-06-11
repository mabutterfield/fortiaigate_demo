variable "aws_profile" {
  type        = string
  description = "AWS CLI SSO profile name."
}

variable "aws_region" {
  type        = string
  description = "AWS region for Bedrock."
  default     = "us-west-2"
}

variable "name_prefix" {
  type        = string
  description = "Prefix for IAM resources."
  default     = "faig-lab"
}

variable "credential_valid_days" {
  type        = number
  description = "Number of days before the IAM policy denies all access."
  default     = 7

  validation {
    condition     = var.credential_valid_days >= 1 && var.credential_valid_days <= 365
    error_message = "credential_valid_days must be between 1 and 365."
  }
}

variable "credential_generation" {
  type        = string
  description = "Change this value to refresh the expiration window."
}

variable "bedrock_model_ids" {
  type        = list(string)
  description = "Allowed Bedrock foundation model IDs. Use the exact Bedrock model ID, including provider version suffixes such as openai.gpt-oss-20b-1:0."
  default     = ["openai.gpt-oss-20b-1:0"]

  validation {
    condition     = length(var.bedrock_model_ids) > 0
    error_message = "bedrock_model_ids must contain at least one model ID."
  }
}

variable "ec2_k3s_state_path" {
  type        = string
  description = "Path to the terraform/aws-ec2-k3s local state file. Used to derive the k3s EIP and allowed_ingress_cidr for Bedrock source IP restrictions."
  default     = "../aws-ec2-k3s/terraform.tfstate"
}

variable "no_ip_restriction" {
  type        = bool
  description = "Disable all source IP restrictions for the Bedrock access key."
  default     = false
}

variable "allowed_source_cidrs" {
  type        = list(string)
  description = "Optional additional public source CIDRs allowed to use the Bedrock access key. The EC2 EIP and allowed_ingress_cidr are loaded from ec2_k3s_state_path unless no_ip_restriction is true."
  default     = []

  validation {
    condition     = alltrue([for cidr in var.allowed_source_cidrs : can(cidrhost(cidr, 0))])
    error_message = "allowed_source_cidrs entries must be valid CIDR blocks."
  }
}

variable "tags" {
  type        = map(string)
  description = "Additional tags for Bedrock IAM resources."
  default     = {}
}
