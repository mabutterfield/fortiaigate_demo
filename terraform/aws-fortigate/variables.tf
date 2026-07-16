variable "aws_profile" {
  type        = string
  description = "AWS CLI SSO profile name."
}

variable "aws_region" {
  type        = string
  description = "AWS region for FortiGate deployment."
}

variable "name_prefix" {
  type        = string
  description = "Name prefix for FortiGate resources."
}

variable "allowed_ingress_cidr" {
  type        = any
  description = "Trusted public CIDR or list of CIDRs allowed to reach FortiGate management."
}

variable "aws_prep_state_path" {
  type        = string
  description = "Path to terraform/aws-prep local state."
  default     = "../aws-prep/terraform.tfstate"
}

variable "aws_ec2_k3s_state_path" {
  type        = string
  description = "Path to terraform/aws-ec2-k3s local state."
  default     = "../aws-ec2-k3s/terraform.tfstate"
}

variable "fortigate_enabled" {
  type        = bool
  description = "Create FortiGate resources from this module."
  default     = true
}

variable "ansible_inventory_output_path" {
  type        = string
  description = "Path where this module writes the generated FortiGate Ansible inventory."
  default     = "../../ansible/inventory/fortigate.generated.ini"
}

variable "ssh_key_name" {
  type        = string
  description = "Existing AWS EC2 key pair name for FortiGate SSH access."
}

variable "ssh_private_key_file" {
  type        = string
  description = "Shared local SSH private key path from terraform/user.tfvars. Accepted for common config consistency; not used by FortiGate."
  default     = ""
}

variable "ec2_pull_github_keys" {
  type        = list(string)
  description = "Shared GitHub usernames for EC2 authorized_keys. Accepted for common config consistency; not used by FortiGate."
  default     = []
}

variable "fortigate_instance_type" {
  type        = string
  description = "EC2 instance type for FortiGate."
  default     = "c6i.xlarge"
}

variable "fortigate_architecture" {
  type        = string
  description = "FortiGate AMI architecture."
  default     = "x86_64"
}

variable "fortigate_version" {
  type        = string
  description = "FortiGate major/minor version to select from AWS Marketplace images."
  default     = "8.0"
}

variable "fortigate_ami_name_override" {
  type        = string
  description = "Optional exact or wildcard FortiGate AMI name override for troubleshooting or pinning."
  default     = ""
}

variable "fortigate_license_type" {
  type        = string
  description = "FortiGate marketplace license type."
  default     = "byol"

  validation {
    condition     = contains(["byol", "payg"], var.fortigate_license_type)
    error_message = "fortigate_license_type must be byol or payg."
  }
}

variable "fortigate_license_mode" {
  type        = string
  description = "FortiGate bootstrap license mode."
  default     = "byol_file"

  validation {
    condition     = contains(["none", "byol_file", "fortiflex_future"], var.fortigate_license_mode)
    error_message = "fortigate_license_mode must be none, byol_file, or fortiflex_future."
  }
}

variable "fortigate_license_file" {
  type        = string
  description = "Optional full local FortiGate BYOL license file path. When empty, fortigate_license_source_dir/fortigate_license_file_name are joined. Keep license files outside Git."
  default     = ""
}

variable "fortigate_license_source_dir" {
  type        = string
  description = "Directory containing the FortiGate BYOL license file. Keep this outside Git."
  default     = "../../../licenses"
}

variable "fortigate_license_file_name" {
  type        = string
  description = "FortiGate BYOL license file name under fortigate_license_source_dir."
  default     = "FGVMSLTM00000000.lic"
}

variable "fortigate_root_volume_size_gb" {
  type        = number
  description = "FortiGate root EBS volume size in GiB."
  default     = 2
}

variable "fortigate_log_volume_size_gb" {
  type        = number
  description = "FortiGate secondary log/data EBS volume size in GiB."
  default     = 30
}

variable "fortigate_admin_port" {
  type        = number
  description = "FortiGate HTTPS management port."
  default     = 443
}

variable "fortigate_admin_timeout_minutes" {
  type        = number
  description = "FortiGate GUI/CLI admin idle timeout in minutes."
  default     = 60

  validation {
    condition     = var.fortigate_admin_timeout_minutes >= 1 && var.fortigate_admin_timeout_minutes <= 480
    error_message = "fortigate_admin_timeout_minutes must be between 1 and 480."
  }
}

variable "fortigate_enable_ssh" {
  type        = bool
  description = "Enable SSH management in the FortiGate bootstrap config."
  default     = true
}

variable "fortigate_enable_api" {
  type        = bool
  description = "Create a FortiGate API admin in the bootstrap config."
  default     = true
}

variable "fortigate_enable_icmp" {
  type        = bool
  description = "Allow ICMP from trusted CIDRs to the FortiGate management ENI for basic reachability testing."
  default     = true
}

variable "fortigate_api_admin" {
  type        = string
  description = "FortiGate API administrator name."
  default     = "apiadmin"
}

variable "fortigate_api_key_length" {
  type        = number
  description = "Generated FortiGate API key length."
  default     = 30
}

variable "tags" {
  type        = map(string)
  description = "Additional tags for AWS resources."
  default     = {}
}
