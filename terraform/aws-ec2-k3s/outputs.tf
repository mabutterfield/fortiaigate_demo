output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.this.id
}

output "public_ip" {
  description = "Elastic public IP for the k3s host."
  value       = aws_eip.this.public_ip
}

output "allowed_ingress_cidr" {
  description = "CIDR allowed to reach SSH/HTTP/HTTPS on the lab instance."
  value       = var.allowed_ingress_cidr
}

output "instance_type" {
  description = "EC2 instance type configured for the k3s host."
  value       = var.instance_type
}

output "selected_availability_zone" {
  description = "Availability Zone selected for the public subnet and k3s EC2 instance."
  value       = local.selected_availability_zone
}

output "ssh_command" {
  description = "SSH command for the k3s host."
  value       = var.ssh_private_key_file != "" ? "ssh -i ${var.ssh_private_key_file} ubuntu@${aws_eip.this.public_ip}" : "ssh ubuntu@${aws_eip.this.public_ip}"
}

output "ansible_inventory" {
  description = "Generated Ansible inventory path."
  value       = local_file.ansible_inventory.filename
}

output "iam_instance_profile_name" {
  description = "IAM instance profile attached to the k3s host."
  value       = var.create_iam_instance_profile ? aws_iam_instance_profile.ec2[0].name : try(data.aws_iam_instance_profile.fortiaigate[0].name, null)
}

output "iam_role_name" {
  description = "IAM role attached to the k3s host through the instance profile. Use this with the ECR Terraform module."
  value       = var.create_iam_instance_profile ? aws_iam_role.ec2[0].name : try(data.aws_iam_instance_profile.fortiaigate[0].role_name, null)
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
