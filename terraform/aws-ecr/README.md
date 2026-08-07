# AWS ECR Terraform Module

This module creates private FortiAIGate ECR repositories and writes generated Ansible registry vars.

Canonical documentation:

- [Container Repository Management](../../docs/container-repository-management.md)
- [Terraform Reference](../../docs/terraform.md)
- [Automated Quick Start](../../docs/quickstart-automated.md)

Quick usage:

```bash
aws sso login --profile <profile-name>
terraform -chdir=terraform/aws-ecr init
terraform -chdir=terraform/aws-ecr fmt
terraform -chdir=terraform/aws-ecr validate
terraform -chdir=terraform/aws-ecr apply
```

Copy `99-local.auto.tfvars.example` to `99-local.auto.tfvars` only when
overriding the tracked defaults in `00-system.auto.tfvars`.

The generated Ansible vars file is written to `../../ansible/group_vars/ecr.generated.yml`.

Scoped ECR pull permissions are created by `terraform/aws-prep`.
