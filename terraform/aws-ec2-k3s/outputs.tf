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
  value       = "ssh ubuntu@${aws_eip.this.public_ip}"
}

output "ansible_inventory" {
  description = "Generated Ansible inventory path."
  value       = local_file.ansible_inventory.filename
}

output "recommended_full_validation_instance_type" {
  description = "Instance type known to work for full FortiAIGate validation."
  value       = "g4dn.4xlarge"
}
