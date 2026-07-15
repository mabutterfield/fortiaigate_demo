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
  default     = "c5.xlarge"

  validation {
    condition = contains([
      "t3.small",
      "t3.medium",
      "t3.large",
      "t3.xlarge",
      "t3.2xlarge",
      "m5.large",
      "m5.xlarge",
      "m5.2xlarge",
      "m4.large",
      "m4.xlarge",
      "m4.2xlarge",
      "c5.large",
      "c5.xlarge",
      "c5.2xlarge",
      "c4.large",
      "c4.xlarge",
      "c4.2xlarge",
    ], var.fortiweb_instance_type)
    error_message = "fortiweb_instance_type must be one of the FortiWeb Marketplace-supported t3, m5, m4, c5, or c4 sizes."
  }
}

variable "fortiweb_architecture" {
  type        = string
  description = "FortiWeb AMI architecture."
  default     = "x86_64"
}

variable "fortiweb_version" {
  type        = string
  description = "FortiWeb major/minor version filter. Use 8.0 to select the latest 8.0.x Marketplace image."
  default     = "8.0"
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
  description = "Optional full local FortiWeb BYOL license file path. When empty, fortiweb_license_source_dir/fortiweb_license_file_name are joined. Keep license files outside Git."
  default     = ""
}

variable "fortiweb_license_source_dir" {
  type        = string
  description = "Directory containing the FortiWeb BYOL license file. Keep this outside Git."
  default     = "../../../licenses"
}

variable "fortiweb_license_file_name" {
  type        = string
  description = "FortiWeb BYOL license file name under fortiweb_license_source_dir."
  default     = "FWBVMSTM00000000.lic"
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

  validation {
    condition     = var.fortiweb_admin_https_port >= 1 && var.fortiweb_admin_https_port <= 65535
    error_message = "fortiweb_admin_https_port must be between 1 and 65535."
  }
}

variable "fortiweb_admin_http_port" {
  type        = number
  description = "FortiWeb HTTP management port."
  default     = 8080

  validation {
    condition     = var.fortiweb_admin_http_port >= 1 && var.fortiweb_admin_http_port <= 65535
    error_message = "fortiweb_admin_http_port must be between 1 and 65535."
  }
}

variable "fortiweb_admin_console_timeout_seconds" {
  type        = number
  description = "FortiWeb GUI/CLI admin idle timeout in seconds."
  default     = 3600

  validation {
    condition     = var.fortiweb_admin_console_timeout_seconds >= 60 && var.fortiweb_admin_console_timeout_seconds <= 28800
    error_message = "fortiweb_admin_console_timeout_seconds must be between 60 and 28800."
  }
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

variable "fortiweb_set_initial_password" {
  type        = bool
  description = "Include initial_passwd in FortiWeb user-data. Leave false to use the AWS Marketplace default admin password behavior: the EC2 instance ID."
  default     = false
}

variable "fortiweb_enable_icmp" {
  type        = bool
  description = "Allow ICMP from trusted CIDRs to the FortiWeb management ENI for basic reachability testing."
  default     = true
}

variable "fortiweb_admin_password" {
  type        = string
  description = "Optional FortiWeb admin password. Leave empty to generate a compliant password."
  default     = ""
  sensitive   = true

  validation {
    condition = (
      var.fortiweb_admin_password == ""
      || can(regex("^(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[$@!%*#?&])[A-Za-z0-9$@!%*#?&]{8,16}$", var.fortiweb_admin_password))
    )
    error_message = "fortiweb_admin_password must be empty or 8-16 characters with lower, upper, number, and one of $@!%*#?&."
  }
}

variable "tags" {
  type        = map(string)
  description = "Additional tags for AWS resources."
  default     = {}
}
