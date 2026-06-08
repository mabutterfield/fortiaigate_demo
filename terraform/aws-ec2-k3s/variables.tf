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
  description = "EC2 GPU instance type. Use g4dn.4xlarge for full FortiAIGate validation."
  default     = "g4dn.xlarge"
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
  description = "Existing IAM instance profile name with ECR read permissions."
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR for the dedicated lab VPC."
  default     = "10.42.0.0/16"
}

variable "public_subnet_cidr" {
  type        = string
  description = "CIDR for the public lab subnet."
  default     = "10.42.1.0/24"
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
