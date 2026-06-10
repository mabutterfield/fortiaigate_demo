# Terraform

Terraform is split into two phase 1 modules:

- `terraform/aws-ecr`: private ECR repositories for FortiAIGate images
- `terraform/aws-ec2-k3s`: AWS network, GPU EC2 instance, Elastic IP, and generated Ansible inventory

Both modules use local Terraform state for phase 1. Remote state is a future enhancement.

## AWS Authentication

Use AWS IAM Identity Center / SSO profiles:

```bash
aws sso login --profile <profile-name>
```

Set the profile in each module's ignored `terraform.tfvars`.

## ECR Module

```bash
cd terraform/aws-ecr
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

Defaults:

- private ECR repositories
- immutable tags
- basic scan-on-push
- AES256 encryption
- lifecycle retention for tagged and untagged images

Set `ec2_pull_role_name` only when Terraform should attach a scoped read policy to an existing EC2 role. Terraform does not create IAM roles.

Terraform writes non-secret registry values to:

```text
ansible/group_vars/ecr.generated.yml
```

The Ansible playbooks load this generated file before `group_vars/all.yml`.

### Import Existing ECR Repositories

If repositories were created manually, import them before `terraform apply`:

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

The import ID must match the real repository name and the configured AWS region.

## AWS EC2 k3s Module

```bash
cd terraform/aws-ec2-k3s
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

This module creates:

- dedicated VPC
- public subnet
- internet gateway and public route table
- security group for SSH, HTTP, and HTTPS from `allowed_ingress_cidr`
- Ubuntu 24.04 GPU EC2 instance
- Elastic IP
- generated Ansible inventory

Terraform writes the inventory to:

```text
ansible/inventory/aws.generated.ini
```

Set `ssh_private_key_file` in `terraform.tfvars` when the EC2 key pair does not use your default SSH key. Terraform includes that path in both:

- `ansible_ssh_private_key_file` in the generated inventory
- the `ssh_command` output as `ssh -i <keypath> ubuntu@<public-ip>`

The module also writes these non-secret network values into the generated inventory so Ansible uses the same plan for k3s:

```ini
aws_vpc_cidr=10.20.0.0/16
aws_public_subnet_cidr=10.20.1.0/24
k3s_cluster_cidr=10.60.0.0/16
k3s_service_cidr=10.70.0.0/16
k3s_cluster_dns=10.70.0.10
```

Override the values in `terraform.tfvars` when the defaults conflict with an existing route domain. Keep AWS VPC, k3s pod, and k3s service networks non-overlapping.

## IAM

IAM role creation is intentionally out of scope for phase 1.

Provide an existing instance profile through `iam_instance_profile_name`. The attached role must be able to pull from ECR, for example through `AmazonEC2ContainerRegistryReadOnly` or the scoped policy attached by the ECR module.

## Instance Sizing

The Terraform default instance type is `g4dn.xlarge` for lower-cost infrastructure smoke testing.

Use a larger override, such as `g4dn.4xlarge`, for full FortiAIGate validation. Internal GPU sizing notes should remain outside this repo.
