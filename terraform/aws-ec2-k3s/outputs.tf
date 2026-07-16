output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.this.id
}

output "aws_profile" {
  description = "AWS CLI profile used by this Terraform module."
  value       = var.aws_profile
}

output "aws_region" {
  description = "AWS region used by this Terraform module."
  value       = var.aws_region
}

output "public_ip" {
  description = "Elastic public IP for the k3s host when k3s_subnet_mode is public."
  value       = local.k3s_public_ip
}

output "private_ip" {
  description = "Private IP for the k3s host."
  value       = aws_instance.this.private_ip
}

output "k3s_subnet_mode" {
  description = "Selected subnet placement mode for the k3s host."
  value       = var.k3s_subnet_mode
}

output "allowed_ingress_cidr" {
  description = "First CIDR allowed to reach SSH/HTTP/HTTPS on the lab instance. Kept for compatibility with older references."
  value       = local.effective_allowed_ingress_cidr
}

output "allowed_ingress_cidrs" {
  description = "CIDRs allowed to reach SSH/HTTP/HTTPS on the lab instance."
  value       = local.effective_allowed_ingress_cidrs
}

output "instance_type" {
  description = "EC2 instance type configured for the k3s host."
  value       = var.instance_type
}

output "ec2_instance_hourly_cost_usd" {
  description = "Estimated On-Demand Linux shared-tenancy EC2 compute cost per hour in USD for the configured instance type and region. Excludes EBS, EIP, data transfer, Bedrock, marketplace, and licensing costs."
  value       = local.ec2_instance_hourly_cost_usd
}

output "ec2_instance_monthly_cost_usd" {
  description = "Estimated 30-day On-Demand Linux shared-tenancy EC2 compute cost in USD for the configured instance type and region, calculated as hourly * 30 * 24. Excludes EBS, EIP, data transfer, Bedrock, marketplace, and licensing costs."
  value       = local.ec2_instance_monthly_cost_usd
}

output "ec2_instance_pricing_location" {
  description = "AWS Price List location string used for the EC2 instance cost estimate."
  value       = local.ec2_pricing_location
}

output "selected_availability_zone" {
  description = "Availability Zone selected for the k3s and appliance subnets."
  value       = local.selected_availability_zone
}

output "vpc_id" {
  description = "VPC ID created by this module."
  value       = aws_vpc.this.id
}

output "internet_gateway_id" {
  description = "Internet gateway ID created by this module."
  value       = aws_internet_gateway.this.id
}

output "ssh_command" {
  description = "SSH command for the k3s host. In private mode this uses the private IP and requires network reachability."
  value       = var.ssh_private_key_file != "" ? "ssh -i ${var.ssh_private_key_file} ubuntu@${local.k3s_ssh_command_host}" : "ssh ubuntu@${local.k3s_ssh_command_host}"
}

output "ansible_inventory" {
  description = "Generated Ansible inventory path."
  value       = local_file.ansible_inventory.filename
}

output "ansible_ports_vars" {
  description = "Generated Ansible demo port vars path."
  value       = local_file.ansible_ports_vars.filename
}

output "demo_port_assignments" {
  description = "Generated HTTP and optional HTTPS demo service port assignments."
  value       = local.demo_port_assignments
}

output "iam_instance_profile_name" {
  description = "IAM instance profile attached to the k3s host."
  value       = local.iam_instance_profile_name
}

output "iam_role_name" {
  description = "IAM role attached to the k3s host through the instance profile."
  value       = local.prep_outputs.ec2_iam_role_name
}

output "network_cidrs" {
  description = "AWS and k3s network CIDRs used by the deployment."
  value = {
    aws_vpc_cidr                       = var.vpc_cidr
    aws_public_subnet_cidr             = var.public_subnet_cidr
    aws_k3s_private_subnet_cidr        = var.k3s_private_subnet_cidr
    aws_fortigate_public_subnet_cidr   = var.fortigate_public_subnet_cidr
    aws_fortigate_internal_subnet_cidr = var.fortigate_internal_subnet_cidr
    aws_fortiweb_public_subnet_cidr    = var.fortiweb_public_subnet_cidr
    aws_fortiweb_internal_subnet_cidr  = var.fortiweb_internal_subnet_cidr
    k3s_cluster_cidr                   = var.k3s_cluster_cidr
    k3s_service_cidr                   = var.k3s_service_cidr
    k3s_cluster_dns                    = var.k3s_cluster_dns
  }
}

output "subnet_ids" {
  description = "Subnet IDs created by this module."
  value = {
    k3s_public         = aws_subnet.public.id
    k3s_private        = aws_subnet.k3s_private.id
    fortigate_public   = aws_subnet.fortigate_public.id
    fortigate_internal = aws_subnet.fortigate_internal.id
    fortiweb_public    = aws_subnet.fortiweb_public.id
    fortiweb_internal  = aws_subnet.fortiweb_internal.id
  }
}

output "route_table_ids" {
  description = "Route table IDs created by this module."
  value = {
    public             = aws_route_table.public.id
    k3s_private        = aws_route_table.k3s_private.id
    fortigate_internal = aws_route_table.fortigate_internal.id
    fortiweb_internal  = aws_route_table.fortiweb_internal.id
  }
}

output "security_group_ids" {
  description = "Security group IDs created by this module."
  value = {
    k3s = aws_security_group.this.id
  }
}

output "ingress_routing" {
  description = "Configured ingress routing placeholders for Phase 2 application URLs."
  value = {
    strategy               = var.ingress_routing_strategy
    base_domain            = var.ingress_base_domain
    host_prefixes          = var.ingress_host_prefixes
    route53_zone_id_set    = var.route53_zone_id != ""
    create_route53_records = var.create_route53_records
    magic_dns_zone         = var.magic_dns_zone
  }
}
