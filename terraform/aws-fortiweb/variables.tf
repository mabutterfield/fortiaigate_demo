variable "aws_profile" {
  type        = string
  description = "AWS CLI SSO profile name."
}

variable "aws_region" {
  type        = string
  description = "AWS region for FortiWeb deployment."
}

variable "name_prefix" {
  type        = string
  description = "Name prefix for FortiWeb resources."
}

variable "allowed_ingress_cidr" {
  type        = any
  description = "Trusted public CIDR or list of CIDRs allowed to reach FortiWeb management."
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

variable "fortiweb_enabled" {
  type        = bool
  description = "Create FortiWeb resources from this module."
  default     = true
}

variable "ssh_key_name" {
  type        = string
  description = "Existing AWS EC2 key pair name for FortiWeb SSH access."
}

variable "fortiweb_instance_type" {
  type        = string
  description = "EC2 instance type for FortiWeb."
  default     = "c6i.xlarge"
}

variable "fortiweb_architecture" {
  type        = string
  description = "FortiWeb AMI architecture."
  default     = "x86_64"
}

variable "fortiweb_version" {
  type        = string
  description = "Optional FortiWeb version filter. Empty selects the latest matching Marketplace image."
  default     = ""
}

variable "fortiweb_ami_name_override" {
  type        = string
  description = "Optional exact or wildcard FortiWeb AMI name override for troubleshooting or pinning."
  default     = ""
}

variable "fortiweb_license_type" {
  type        = string
  description = "FortiWeb marketplace license type."
  default     = "byol"

  validation {
    condition     = contains(["byol", "payg"], var.fortiweb_license_type)
    error_message = "fortiweb_license_type must be byol or payg."
  }
}

variable "fortiweb_license_mode" {
  type        = string
  description = "FortiWeb bootstrap license mode."
  default     = "byol_file"

  validation {
    condition     = contains(["none", "byol_file", "fortiflex_future"], var.fortiweb_license_mode)
    error_message = "fortiweb_license_mode must be none, byol_file, or fortiflex_future."
  }
}

variable "fortiweb_license_file" {
  type        = string
  description = "Local FortiWeb BYOL license file path. Keep this outside Git."
  default     = "../../licenses/FWB.lic"
}

variable "fortiweb_config_file" {
  type        = string
  description = "Local FortiWeb command/config file path to upload to the prep-owned S3 bucket."
  default     = ""
}

variable "fortiweb_admin_https_port" {
  type        = number
  description = "FortiWeb HTTPS management port."
  default     = 8443
}

variable "fortiweb_admin_http_port" {
  type        = number
  description = "FortiWeb HTTP management port."
  default     = 8080
}

variable "fortiweb_enable_ssh" {
  type        = bool
  description = "Enable SSH management when supported by FortiWeb bootstrap syntax."
  default     = true
}

variable "fortiweb_enable_api" {
  type        = bool
  description = "Enable FortiWeb API access when supported by FortiWeb bootstrap syntax."
  default     = true
}

variable "fortiweb_admin_password" {
  type        = string
  description = "Optional FortiWeb admin password. Leave empty until testing proves whether instance ID default works."
  default     = ""
  sensitive   = true
}

variable "tags" {
  type        = map(string)
  description = "Additional tags for AWS resources."
  default     = {}
}
