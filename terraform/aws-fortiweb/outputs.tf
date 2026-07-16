output "fortiweb_instance_id" {
  description = "FortiWeb EC2 instance ID."
  value       = try(aws_instance.this[0].id, null)
}

output "fortiweb_ami_id" {
  description = "AMI ID selected for FortiWeb."
  value       = try(data.aws_ami.fortiweb[0].id, null)
}

output "fortiweb_ami_name" {
  description = "AMI name selected for FortiWeb."
  value       = try(data.aws_ami.fortiweb[0].name, null)
}

output "fortiweb_public_ip" {
  description = "Prep-owned FortiWeb EIP public IP."
  value       = local.fortiweb_eip_public_ip
}

output "fortiweb_public_private_ip" {
  description = "Private IP on FortiWeb port1/public ENI."
  value       = try(aws_network_interface.public[0].private_ip, null)
}

output "fortiweb_internal_ip" {
  description = "Private IP on FortiWeb port2/internal ENI."
  value       = try(aws_network_interface.internal[0].private_ip, null)
}

output "fortiweb_public_network_interface_id" {
  description = "FortiWeb port1/public ENI ID."
  value       = try(aws_network_interface.public[0].id, null)
}

output "ansible_group_vars" {
  description = "Generated FortiWeb Ansible group vars path."
  value       = local_file.ansible_group_vars.filename
}

output "fortiweb_internal_network_interface_id" {
  description = "FortiWeb port2/internal ENI ID."
  value       = try(aws_network_interface.internal[0].id, null)
}

output "fortiweb_admin_url" {
  description = "FortiWeb HTTPS admin URL."
  value       = local.fortiweb_eip_public_ip != null ? "https://${local.fortiweb_eip_public_ip}:${var.fortiweb_admin_https_port}" : null
}

output "fortiweb_http_admin_url" {
  description = "FortiWeb HTTP admin URL."
  value       = local.fortiweb_eip_public_ip != null ? "http://${local.fortiweb_eip_public_ip}:${var.fortiweb_admin_http_port}" : null
}

output "fortiweb_data_plane_tcp_ports" {
  description = "FortiWeb data-plane TCP listener ports allowed by this module."
  value       = distinct(var.fortiweb_data_plane_tcp_ports)
}

output "fortiweb_data_plane_public_cidrs" {
  description = "Public CIDRs allowed to FortiWeb data-plane listener ports."
  value       = local.fortiweb_data_plane_public_cidrs
}

output "fortiweb_ssh_command" {
  description = "SSH command for FortiWeb management."
  value       = local.fortiweb_eip_public_ip != null ? "ssh admin@${local.fortiweb_eip_public_ip}" : null
}

output "fortiweb_username" {
  description = "Default FortiWeb administrator username."
  value       = "admin"
}

output "fortiweb_admin_password" {
  description = "FortiWeb admin password when fortiweb_set_initial_password is true. Terraform state contains this value when set."
  value       = var.fortiweb_set_initial_password ? local.fortiweb_admin_password : null
  sensitive   = true
}

output "fortiweb_initial_password_hint" {
  description = "FortiWeb initial password hint."
  value       = var.fortiweb_set_initial_password ? (nonsensitive(var.fortiweb_admin_password) == "" ? "Run: terraform output -raw fortiweb_admin_password" : "Use the sensitive fortiweb_admin_password value from local tfvars.") : "No initial_passwd is set in user-data. Use the FortiWeb EC2 instance ID as the initial admin password."
}

output "fortiweb_cloudinit_bucket_name" {
  description = "S3 bucket used by FortiWeb cloud-init."
  value       = local.fortiweb_cloudinit_bucket_name
}

output "fortiweb_cloudinit_config_key" {
  description = "S3 object key for the FortiWeb command/config file."
  value       = local.fortiweb_cloudinit_config_key
}

output "fortiweb_cloudinit_license_key" {
  description = "S3 object key for the FortiWeb BYOL license file."
  value       = var.fortiweb_license_mode == "byol_file" ? local.fortiweb_cloudinit_license_key : null
}

output "fortiweb_license_mode" {
  description = "FortiWeb license bootstrap mode."
  value       = var.fortiweb_license_mode
}
