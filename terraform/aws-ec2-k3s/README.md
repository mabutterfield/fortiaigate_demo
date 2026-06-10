# AWS EC2 k3s Terraform Module

This module creates the phase 1 AWS EC2/k3s lab infrastructure and writes the generated Ansible inventory.

Canonical documentation:

- [../../docs/terraform.md](../../docs/terraform.md)
- [../../docs/aws-k3s-foundation.md](../../docs/aws-k3s-foundation.md)
- [../../docs/deployment-runbook.md](../../docs/deployment-runbook.md)

Quick usage:

```bash
cp terraform.tfvars.example terraform.tfvars
aws sso login --profile <profile-name>
terraform init
terraform fmt
terraform validate
terraform apply
```

The generated inventory is written to `../../ansible/inventory/aws.generated.ini`.

Set `ssh_private_key_file` in `terraform.tfvars` when the EC2 key pair does not use your default SSH key. Terraform uses that value in both the generated Ansible inventory and the `ssh_command` output.
