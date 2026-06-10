# AWS ECR Repositories

This module creates private FortiAIGate ECR repositories. It manages registry infrastructure only; image loading, tagging, and pushing are handled by Ansible.

## Usage

```bash
cd terraform/aws-ecr
cp terraform.tfvars.example terraform.tfvars
aws sso login --profile <profile-name>
terraform init
terraform fmt
terraform validate
terraform apply
```

Set `ec2_pull_role_name` only when you want Terraform to attach a scoped ECR read policy to an existing EC2 role. Terraform does not create IAM roles.

Terraform writes non-secret ECR connection data to `../../ansible/group_vars/ecr.generated.yml` by default. The Ansible publish/deploy playbooks load this generated file before `group_vars/all.yml`, so local ignored vars can still override it.

## Import Existing Repositories

If the repositories were created manually, import them into this module instead of recreating them:

```bash
terraform import 'aws_ecr_repository.this["api"]' fortiaigate/api
terraform import 'aws_ecr_repository.this["core"]' fortiaigate/core
terraform import 'aws_ecr_repository.this["webui"]' fortiaigate/webui
terraform import 'aws_ecr_repository.this["scanner"]' fortiaigate/scanner
terraform import 'aws_ecr_repository.this["logd"]' fortiaigate/logd
terraform import 'aws_ecr_repository.this["license_manager"]' fortiaigate/license_manager
terraform import 'aws_ecr_repository.this["triton-models"]' fortiaigate/triton-models
terraform import 'aws_ecr_repository.this["custom-triton"]' fortiaigate/custom-triton
```

## Defaults

- Repositories are private ECR repositories.
- Tags are immutable.
- Basic scan-on-push is enabled.
- Repositories use AES256 encryption.
- Lifecycle policy retains the newest tagged images and expires untagged images after 7 days.
