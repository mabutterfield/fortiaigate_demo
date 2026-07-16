variable "aws_profile" {
  type        = string
  description = "AWS CLI SSO profile name."
}

variable "aws_region" {
  type        = string
  description = "AWS region for shared AWS prep resources."
}

variable "name_prefix" {
  type        = string
  description = "Name prefix for shared AWS prep resources."
}

variable "ssh_key_name" {
  type        = string
  description = "Shared EC2 key pair name from terraform/user.tfvars. Accepted for common config consistency; not used by AWS prep."
}

variable "ssh_private_key_file" {
  type        = string
  description = "Shared local SSH private key path from terraform/user.tfvars. Accepted for common config consistency; not used by AWS prep."
  default     = ""
}

variable "ec2_pull_github_keys" {
  type        = list(string)
  description = "Shared GitHub usernames for EC2 authorized_keys. Accepted for common config consistency; not used by AWS prep."
  default     = []
}

variable "allowed_ingress_cidr" {
  type        = any
  description = "Trusted public CIDR or list of CIDRs allowed to reach lab management and demo endpoints."

  validation {
    condition = (
      can(cidrhost(tostring(var.allowed_ingress_cidr), 0))
      || (
        can(tolist(var.allowed_ingress_cidr)[0])
        && can([for cidr in tolist(var.allowed_ingress_cidr) : cidrhost(cidr, 0)])
      )
    )
    error_message = "allowed_ingress_cidr must be a valid CIDR block or non-empty list of valid CIDR blocks."
  }
}

variable "tags" {
  type        = map(string)
  description = "Additional tags for AWS resources."
  default     = {}
}

variable "registry_backend" {
  type        = string
  description = "Registry backend used by the deployment. ecr enables scoped ECR pull permissions."
  default     = "ecr"

  validation {
    condition     = contains(["ecr", "local"], var.registry_backend)
    error_message = "registry_backend must be ecr or local."
  }
}

variable "aws_ecr_state_path" {
  type        = string
  description = "Path to terraform/aws-ecr local state. Used for scoped ECR pull policy repository ARNs."
  default     = "../aws-ecr/terraform.tfstate"
}

variable "ec2_iam_role_name" {
  type        = string
  description = "Optional EC2 IAM role name. Leave empty to derive from name_prefix."
  default     = ""
}

variable "ec2_instance_profile_name" {
  type        = string
  description = "Optional EC2 instance profile name. Leave empty to derive from name_prefix."
  default     = ""
}

variable "ec2_iam_role_managed_policy_arns" {
  type        = list(string)
  description = "Optional managed policy ARNs to attach to the k3s EC2 IAM role."
  default     = []
}

variable "allocate_eips" {
  type = object({
    k3s       = bool
    fortigate = bool
    fortiweb  = bool
  })
  description = "Public EIPs to preallocate for the lab entry points."
  default = {
    k3s       = true
    fortigate = false
    fortiweb  = false
  }
}

variable "fortiweb_enabled" {
  type        = bool
  description = "Create shared FortiWeb prep resources, including the cloud-init S3 bucket and EC2 instance profile."
  default     = false
}

variable "fortiweb_cloudinit_bucket_name" {
  type        = string
  description = "Optional S3 bucket name for FortiWeb cloud-init config and license objects. Leave empty to derive a name from name_prefix, account ID, and region."
  default     = ""

  validation {
    condition     = var.fortiweb_cloudinit_bucket_name == "" || can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.fortiweb_cloudinit_bucket_name))
    error_message = "fortiweb_cloudinit_bucket_name must be empty or a valid S3 bucket name."
  }
}

variable "fortiweb_cloudinit_bucket_force_destroy" {
  type        = bool
  description = "Allow Terraform destroy to delete the FortiWeb cloud-init bucket even when it contains objects. Leave false unless this is a disposable lab bucket."
  default     = false
}

variable "fortiweb_cloudinit_config_key" {
  type        = string
  description = "Default S3 object key where the FortiWeb command/config file will be stored."
  default     = "fortiweb/cloud-init/config.txt"
}

variable "fortiweb_cloudinit_license_key" {
  type        = string
  description = "Default S3 object key where the FortiWeb BYOL license file will be stored."
  default     = "fortiweb/cloud-init/FWB.lic"
}

variable "enable_bedrock_iam" {
  type        = bool
  description = "Create temporary IAM user credentials for FortiAIGate Bedrock provider setup."
  default     = true
}

variable "enable_ec2_bedrock_iam" {
  type        = bool
  description = "Attach scoped Bedrock invoke permissions to the k3s EC2 IAM role for in-cluster direct model clients."
  default     = true
}

variable "bedrock_credential_valid_days" {
  type        = number
  description = "Number of days before the Bedrock IAM policy denies all access."
  default     = 7

  validation {
    condition     = var.bedrock_credential_valid_days >= 1 && var.bedrock_credential_valid_days <= 365
    error_message = "bedrock_credential_valid_days must be between 1 and 365."
  }
}

variable "bedrock_credential_generation" {
  type        = string
  description = "Change this value to refresh the Bedrock IAM expiration window."
}

variable "bedrock_model_ids" {
  type        = list(string)
  description = "Allowed Bedrock foundation model IDs."
  default     = ["openai.gpt-oss-20b-1:0"]

  validation {
    condition     = length(var.bedrock_model_ids) > 0
    error_message = "bedrock_model_ids must contain at least one model ID."
  }
}

variable "bedrock_allowed_regions" {
  type        = list(string)
  description = "AWS regions where the Bedrock access key can invoke the selected models."
  default     = ["us-east-1", "us-east-2", "us-west-1", "us-west-2"]

  validation {
    condition     = length(var.bedrock_allowed_regions) > 0
    error_message = "bedrock_allowed_regions must contain at least one region or \"*\"."
  }
}

variable "bedrock_no_ip_restriction" {
  type        = bool
  description = "Disable source IP restrictions for the Bedrock access key."
  default     = false
}

variable "bedrock_allowed_source_cidrs" {
  type        = list(string)
  description = "Optional additional public source CIDRs allowed to use the Bedrock access key."
  default     = []

  validation {
    condition     = alltrue([for cidr in var.bedrock_allowed_source_cidrs : can(cidrhost(cidr, 0))])
    error_message = "bedrock_allowed_source_cidrs entries must be valid CIDR blocks."
  }
}
