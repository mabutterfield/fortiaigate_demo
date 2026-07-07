# AWS ECR Terraform Module

This module creates private FortiAIGate ECR repositories and writes generated Ansible registry vars.

Canonical documentation:

- [../../docs/terraform.md](../../docs/terraform.md)
- [../../docs/ECR.md](../../docs/ECR.md)
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

The generated Ansible vars file is written to `../../ansible/group_vars/ecr.generated.yml`.

Scoped ECR pull permissions are created by `terraform/aws-prep`.
