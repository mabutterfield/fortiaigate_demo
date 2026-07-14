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

variable "aws_pricing_location_override" {
  type        = string
  description = "Optional AWS Price List location string override, for example US East (N. Virginia). Leave empty to derive it from aws_region."
  default     = ""
}

variable "availability_zone" {
  type        = string
  description = "Optional Availability Zone for the k3s and appliance subnets. Leave empty to auto-select the first AZ that offers instance_type."
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

variable "ec2_pull_github_keys" {
  type        = list(string)
  description = "Optional GitHub usernames whose public SSH keys should be imported into the ubuntu user's authorized_keys on first boot."
  default     = []

  validation {
    condition = alltrue([
      for username in var.ec2_pull_github_keys : can(regex("^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$", username))
    ])
    error_message = "ec2_pull_github_keys entries must be valid GitHub usernames."
  }
}

variable "allowed_ingress_cidr" {
  type        = any
  description = "Shared trusted source CIDR or list of CIDRs from terraform/common.tfvars. terraform/aws-prep is the effective source of truth for EC2 security group rules."
}

variable "aws_prep_state_path" {
  type        = string
  description = "Path to terraform/aws-prep local state. Used for IAM profile, trusted CIDR, and prep-owned EIP allocation."
  default     = "../aws-prep/terraform.tfstate"
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
  description = "CIDR for the public k3s lab subnet. Kept as public_subnet_cidr for compatibility with existing tfvars."
  default     = "10.20.1.0/24"

  validation {
    condition     = can(cidrhost(var.public_subnet_cidr, 0))
    error_message = "public_subnet_cidr must be a valid CIDR block."
  }
}

variable "k3s_subnet_mode" {
  type        = string
  description = "Subnet placement for the k3s host. public keeps the current direct-access behavior; private places k3s in the private subnet without a public IP."
  default     = "public"

  validation {
    condition     = contains(["public", "private"], var.k3s_subnet_mode)
    error_message = "k3s_subnet_mode must be public or private."
  }
}

variable "k3s_private_subnet_cidr" {
  type        = string
  description = "CIDR for the optional private k3s subnet used when k3s_subnet_mode is private."
  default     = "10.20.2.0/24"

  validation {
    condition     = can(cidrhost(var.k3s_private_subnet_cidr, 0))
    error_message = "k3s_private_subnet_cidr must be a valid CIDR block."
  }
}

variable "fortigate_public_subnet_cidr" {
  type        = string
  description = "CIDR for the FortiGate public/front-end subnet placeholder."
  default     = "10.20.10.0/24"

  validation {
    condition     = can(cidrhost(var.fortigate_public_subnet_cidr, 0))
    error_message = "fortigate_public_subnet_cidr must be a valid CIDR block."
  }
}

variable "fortigate_internal_subnet_cidr" {
  type        = string
  description = "CIDR for the FortiGate internal subnet."
  default     = "10.20.20.0/24"

  validation {
    condition     = can(cidrhost(var.fortigate_internal_subnet_cidr, 0))
    error_message = "fortigate_internal_subnet_cidr must be a valid CIDR block."
  }
}

variable "fortiweb_public_subnet_cidr" {
  type        = string
  description = "CIDR for the FortiWeb public/front-end subnet placeholder."
  default     = "10.20.11.0/24"

  validation {
    condition     = can(cidrhost(var.fortiweb_public_subnet_cidr, 0))
    error_message = "fortiweb_public_subnet_cidr must be a valid CIDR block."
  }
}

variable "fortiweb_internal_subnet_cidr" {
  type        = string
  description = "CIDR for the FortiWeb internal subnet."
  default     = "10.20.21.0/24"

  validation {
    condition     = can(cidrhost(var.fortiweb_internal_subnet_cidr, 0))
    error_message = "fortiweb_internal_subnet_cidr must be a valid CIDR block."
  }
}

variable "k3s_private_default_route_network_interface_id" {
  type        = string
  description = "Optional network interface ID for the private k3s subnet default route, typically a FortiGate internal/traffic interface. Leave empty until an appliance route target exists."
  default     = ""
}

variable "appliance_ingress_to_k3s_enabled" {
  type        = bool
  description = "Allow HTTP/HTTPS from the FortiGate and FortiWeb public subnet CIDRs to the k3s security group for appliance proxy/SNAT test paths."
  default     = true
}

variable "additional_ingress_tcp_ports" {
  type        = set(number)
  description = "Additional TCP ports to allow from allowed_ingress_cidr beyond the generated demo HTTP/HTTPS port assignments."
  default     = []

  validation {
    condition = alltrue([
      for port in var.additional_ingress_tcp_ports : port >= 1 && port <= 65535
    ])
    error_message = "additional_ingress_tcp_ports values must be valid TCP ports between 1 and 65535."
  }
}

variable "demo_http_base_port" {
  type        = number
  description = "Base NodePort for generated HTTP demo services. Slots are openwebui, chatbot, demo_home, litellm, and mcp."
  default     = 30080

  validation {
    condition     = var.demo_http_base_port >= 30000 && var.demo_http_base_port + 4 <= 32767
    error_message = "demo_http_base_port must allow five Kubernetes NodePorts between 30000 and 32767."
  }
}

variable "demo_https_base_port" {
  type        = number
  description = "Base host port for generated optional HTTPS demo gateway services. The offset matches demo_http_base_port."
  default     = 30443

  validation {
    condition     = var.demo_https_base_port >= 1 && var.demo_https_base_port + 4 <= 65535
    error_message = "demo_https_base_port must allow five valid TCP ports between 1 and 65535."
  }
}

variable "ansible_ports_vars_output_path" {
  type        = string
  description = "Path for generated Ansible demo port variables, relative to this Terraform module."
  default     = "../../ansible/group_vars/ports.generated.yml"
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

# Phase 2 routing placeholders. These variables are intentionally defined now
# so AWS and local Ubuntu deployments can share the same vocabulary when app
# ingress manifests are added. Terraform does not create DNS records yet.

variable "ingress_routing_strategy" {
  type        = string
  description = "Application ingress routing strategy placeholder. path_based is the no-domain default; port_based supports root-path apps; host_based is for future DNS-backed demos."
  default     = "path_based"

  validation {
    condition     = contains(["path_based", "port_based", "host_based"], var.ingress_routing_strategy)
    error_message = "ingress_routing_strategy must be path_based, port_based, or host_based."
  }
}

variable "ingress_base_domain" {
  type        = string
  description = "Optional DNS base domain for future host_based routing, for example example.com. Leave empty for path_based or port_based demos."
  default     = ""
}

variable "ingress_host_prefixes" {
  type        = map(string)
  description = "Hostname prefixes for future host_based routing. Combined with ingress_base_domain when DNS-backed routing is implemented."
  default = {
    faig           = "faig"
    chatbot        = "chatbot"
    openwebui      = "openwebui"
    direct_bedrock = "direct-bedrock"
    mcp_echo       = "mcp-echo"
  }
}

variable "route53_zone_id" {
  type        = string
  description = "Optional Route53 hosted zone ID for future DNS record creation when ingress_routing_strategy is host_based."
  default     = ""
}

variable "create_route53_records" {
  type        = bool
  description = "Future placeholder for creating Route53 records for host_based routing. Currently documented only; no DNS resources are created by this module."
  default     = false
}

variable "magic_dns_zone" {
  type        = string
  description = "Optional magic DNS suffix for no-owned-domain labs, such as sslip.io or nip.io. Placeholder for future generated URLs."
  default     = "sslip.io"
}
