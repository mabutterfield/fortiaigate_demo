output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.this.id
}

output "public_ip" {
  description = "Elastic public IP for the k3s host."
  value       = aws_eip.this.public_ip
}

output "ssh_command" {
  description = "SSH command for the k3s host."
  value       = var.ssh_private_key_file != "" ? "ssh -i ${var.ssh_private_key_file} ubuntu@${aws_eip.this.public_ip}" : "ssh ubuntu@${aws_eip.this.public_ip}"
}

output "ansible_inventory" {
  description = "Generated Ansible inventory path."
  value       = local_file.ansible_inventory.filename
}

output "network_cidrs" {
  description = "AWS and k3s network CIDRs used by the deployment."
  value = {
    aws_vpc_cidr           = var.vpc_cidr
    aws_public_subnet_cidr = var.public_subnet_cidr
    k3s_cluster_cidr       = var.k3s_cluster_cidr
    k3s_service_cidr       = var.k3s_service_cidr
    k3s_cluster_dns        = var.k3s_cluster_dns
  }
}

output "recommended_full_validation_instance_type" {
  description = "Instance type known to work for full FortiAIGate validation."
  value       = "g4dn.4xlarge"
}
