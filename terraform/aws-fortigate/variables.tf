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

variable "ssh_key_name" {
  type        = string
  description = "Existing AWS EC2 key pair name for FortiGate SSH access."
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
  default     = "7.6"
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
  description = "Local FortiGate BYOL license file path. Keep this outside Git."
  default     = "../../licenses/FGT.lic"
}

variable "fortigate_admin_port" {
  type        = number
  description = "FortiGate HTTPS management port."
  default     = 8443
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
