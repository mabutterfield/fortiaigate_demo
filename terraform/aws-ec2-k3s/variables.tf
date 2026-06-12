variable "aws_profile" {
  type        = string
  description = "AWS CLI SSO profile name."
}

variable "aws_region" {
  type        = string
  description = "AWS region for the lab."
  default     = "us-east-1"
}

variable "name_prefix" {
  type        = string
  description = "Name prefix for AWS resources."
  default     = "FAIG-demo"
}

variable "instance_type" {
  type        = string
  description = "EC2 GPU instance type. g4dn.4xlarge is the default lab size; consider g6.8xlarge for production-like validation."
  default     = "g4dn.4xlarge"
}

variable "availability_zone" {
  type        = string
  description = "Optional Availability Zone for the public subnet and EC2 instance. Leave empty to auto-select the first AZ that offers instance_type."
  default     = ""
}

variable "ssh_key_name" {
  type        = string
  description = "Existing AWS EC2 key pair name."
}

variable "ssh_private_key_file" {
  type        = string
  description = "Optional local private key path to include in the generated Ansible inventory."
  default     = ""
}

variable "allowed_ingress_cidr" {
  type        = string
  description = "CIDR allowed to reach SSH/HTTP/HTTPS on the lab instance."
}

variable "iam_instance_profile_name" {
  type        = string
  description = "IAM instance profile name. Existing profile when create_iam_instance_profile is false; profile to create when true. Leave empty with create_iam_instance_profile=true to use name_prefix."
  default     = ""
}

variable "create_iam_instance_profile" {
  type        = bool
  description = "Create an EC2 IAM role and instance profile for the k3s host instead of looking up an existing profile."
  default     = false
}

variable "iam_role_name" {
  type        = string
  description = "Optional IAM role name to create when create_iam_instance_profile is true. Leave empty to use name_prefix."
  default     = ""
}

variable "iam_role_managed_policy_arns" {
  type        = list(string)
  description = "Optional managed policy ARNs to attach to the created EC2 IAM role. ECR and Bedrock scoped policies can also be attached by their dedicated Terraform modules."
  default     = []
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR for the dedicated lab VPC."
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be a valid CIDR block."
  }
}

variable "public_subnet_cidr" {
  type        = string
  description = "CIDR for the public lab subnet."
  default     = "10.20.1.0/24"

  validation {
    condition     = can(cidrhost(var.public_subnet_cidr, 0))
    error_message = "public_subnet_cidr must be a valid CIDR block."
  }
}

variable "k3s_cluster_cidr" {
  type        = string
  description = "k3s pod network CIDR passed to the Ansible bootstrap inventory."
  default     = "10.60.0.0/16"

  validation {
    condition     = can(cidrhost(var.k3s_cluster_cidr, 0))
    error_message = "k3s_cluster_cidr must be a valid CIDR block."
  }
}

variable "k3s_service_cidr" {
  type        = string
  description = "k3s service network CIDR passed to the Ansible bootstrap inventory."
  default     = "10.70.0.0/16"

  validation {
    condition     = can(cidrhost(var.k3s_service_cidr, 0))
    error_message = "k3s_service_cidr must be a valid CIDR block."
  }
}

variable "k3s_cluster_dns" {
  type        = string
  description = "k3s cluster DNS service IP. This must be inside k3s_service_cidr."
  default     = "10.70.0.10"
}

variable "root_volume_size_gb" {
  type        = number
  description = "Root EBS volume size in GiB."
  default     = 100
}

variable "inventory_output_path" {
  type        = string
  description = "Path for generated Ansible inventory, relative to this Terraform module."
  default     = "../../ansible/inventory/aws.generated.ini"
}

variable "tags" {
  type        = map(string)
  description = "Additional tags for AWS resources."
  default     = {}
}
