output "fortigate_instance_id" {
  description = "FortiGate EC2 instance ID."
  value       = try(aws_instance.this[0].id, null)
}

output "fortigate_ami_id" {
  description = "AMI ID selected for FortiGate."
  value       = try(data.aws_ami.fortigate[0].id, null)
}

output "fortigate_ami_name" {
  description = "AMI name selected for FortiGate."
  value       = try(data.aws_ami.fortigate[0].name, null)
}

output "fortigate_public_ip" {
  description = "Prep-owned FortiGate EIP public IP."
  value       = local.fortigate_eip_public_ip
}

output "fortigate_public_private_ip" {
  description = "Private IP on FortiGate port1/public ENI."
  value       = try(aws_network_interface.public[0].private_ip, null)
}

output "fortigate_internal_ip" {
  description = "Private IP on FortiGate port2/internal ENI."
  value       = try(aws_network_interface.internal[0].private_ip, null)
}

output "fortigate_public_network_interface_id" {
  description = "FortiGate port1/public ENI ID."
  value       = try(aws_network_interface.public[0].id, null)
}

output "fortigate_internal_network_interface_id" {
  description = "FortiGate port2/internal ENI ID."
  value       = try(aws_network_interface.internal[0].id, null)
}

output "fortigate_admin_url" {
  description = "FortiGate HTTPS admin URL."
  value       = local.fortigate_eip_public_ip != null ? "https://${local.fortigate_eip_public_ip}:${var.fortigate_admin_port}" : null
}

output "fortigate_api_url" {
  description = "FortiGate REST API base URL."
  value       = local.fortigate_eip_public_ip != null ? "https://${local.fortigate_eip_public_ip}:${var.fortigate_admin_port}/api/v2" : null
}

output "fortigate_ssh_command" {
  description = "SSH command for FortiGate management."
  value       = local.fortigate_eip_public_ip != null ? "ssh admin@${local.fortigate_eip_public_ip}" : null
}

output "fortigate_username" {
  description = "Default FortiGate administrator username."
  value       = "admin"
}

output "fortigate_initial_password_hint" {
  description = "FortiGate initial password hint."
  value       = "Initial admin password is the FortiGate EC2 instance ID from fortigate_instance_id."
}

output "fortigate_api_admin" {
  description = "FortiGate API administrator username."
  value       = var.fortigate_enable_api ? var.fortigate_api_admin : null
}

output "fortigate_api_key" {
  description = "Generated FortiGate API key. Terraform state contains this value."
  value       = try(random_string.fortigate_api_key[0].result, null)
  sensitive   = true
}

output "fortigate_license_mode" {
  description = "FortiGate license bootstrap mode."
  value       = var.fortigate_license_mode
}
