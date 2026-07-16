# AWS ECR Terraform Module

This module creates private FortiAIGate ECR repositories and writes generated Ansible registry vars.

Canonical documentation:

- [../../docs/terraform.md](../../docs/terraform.md)
- [../../docs/ECR.md](../../docs/ECR.md)
- [../../docs/deployment-runbook.md](../../docs/deployment-runbook.md)

Quick usage:

```bash
aws sso login --profile <profile-name>
terraform init
terraform fmt
terraform validate
terraform apply
```

Copy `99-local.auto.tfvars.example` to `99-local.auto.tfvars` only when
overriding the tracked defaults in `00-system.auto.tfvars`.

The generated Ansible vars file is written to `../../ansible/group_vars/ecr.generated.yml`.

Scoped ECR pull permissions are created by `terraform/aws-prep`.
