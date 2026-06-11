# Terraform

Terraform is split into three phase 1 modules:

- `terraform/aws-ecr`: private ECR repositories for FortiAIGate images
- `terraform/aws-bedrock`: temporary IAM credentials for manual FortiAIGate Bedrock provider setup
- `terraform/aws-ec2-k3s`: AWS network, GPU EC2 instance, Elastic IP, and generated Ansible inventory

All modules use local Terraform state for phase 1. Remote state is a future enhancement.

## AWS Authentication

Use AWS IAM Identity Center / SSO profiles:

```bash
aws sso login --profile <profile-name>
```

Set the profile in each module's ignored `terraform.tfvars`.

Useful preflight checks:

```bash
aws configure list-profiles
aws sts get-caller-identity --profile <profile-name>
```

Terraform `.terraform.lock.hcl` files are tracked on purpose to pin provider versions. Do not commit `.terraform/`, real `.tfvars`, state, plans, or generated secrets.

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

Set `ec2_pull_role_name` to the `terraform/aws-ec2-k3s` `iam_role_name` output when Terraform should attach a scoped read policy to the k3s host role. This works with either an existing role looked up by the EC2 module or a role created by the EC2 module.

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

## Bedrock Module

```bash
cd terraform/aws-bedrock
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt
terraform validate
terraform apply
```

Set `bedrock_model_ids` after choosing models and confirming model access in the AWS account/region. Use exact Bedrock model IDs, for example `openai.gpt-oss-20b-1:0`, not short display names. This module creates a dedicated IAM user and access key for the FortiAIGate GUI.

Set `bedrock_allowed_regions` to the commercial US regions where those model IDs should be invokable. Use `["*"]` only when the selected model IDs should be allowed in any region.

By default, Bedrock source IP restrictions are derived from `terraform/aws-ec2-k3s` local state: the k3s host EIP as `<eip>/32` and the EC2 `allowed_ingress_cidr`. Set `no_ip_restriction = true` to disable that deny, or use `allowed_source_cidrs` for extra CIDRs.

The secret access key is a sensitive Terraform output and is stored in Terraform state. Do not commit state or real `terraform.tfvars`.

See [Bedrock.md](Bedrock.md) for credential handling and GUI setup details.

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
- optional EC2 IAM role and instance profile
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

By default, the EC2 module uses an existing instance profile:

```hcl
create_iam_instance_profile = false
iam_instance_profile_name   = "existing-profile-name"
```

To let Terraform create the EC2 role and instance profile:

```hcl
create_iam_instance_profile = true
iam_role_name               = "fortiaigate-demo-ec2-role"
iam_instance_profile_name   = "fortiaigate-demo-ec2-profile"
```

If `iam_role_name` or `iam_instance_profile_name` are empty in creation mode, Terraform derives names from `name_prefix`.

After applying `terraform/aws-ec2-k3s`, pass the `iam_role_name` output to:

- `terraform/aws-ecr.ec2_pull_role_name` for scoped private ECR pull access

Bedrock does not use the EC2 role because FortiAIGate currently asks for Access Key ID and Secret Access Key fields in the provider GUI.

## Instance Sizing

The Terraform default instance type is `g4dn.4xlarge`.

Use `g6.8xlarge` for a stronger production-like L4 validation target. Use `g6.4xlarge` when you want a lower-cost official L4 lab candidate.

Approximate instance sizing guidance:

| Instance | GPU | GPU RAM | vCPU | RAM | Local NVMe | Use |
|---|---:|---:|---:|---:|---:|---|
| `g4dn.xlarge` | T4 x1 | 16 GB | 4 | 16 GB | 125 GB | Kubernetes and automation smoke test only |
| `g4dn.4xlarge` | T4 x1 | 16 GB | 16 | 64 GB | 225 GB | Default cost-conscious lab size |
| `g6.4xlarge` | L4 x1 | 24 GB | 16 | 64 GB | 600 GB | Lower-cost official L4 lab candidate |
| `g5.8xlarge` | A10G x1 | 24 GB | 32 | 128 GB | 900 GB | Production-like A10G validation |
| `g6.8xlarge` | L4 x1 | 24 GB | 32 | 128 GB | 900 GB | Recommended production-like L4 validation |
| `g6.12xlarge` | L4 x4 | 96 GB | 48 | 192 GB | 3,800 GB | Multi-GPU validation |
| `g6e.4xlarge` | L40S x1 | 48 GB | 16 | 128 GB | 940 GB | Larger single-GPU VRAM evaluation |
| `g7e.4xlarge` | RTX PRO 6000 Blackwell x1 | 96 GB | 16 | 128 GB | 940 GB | Future-looking large-VRAM evaluation |

AWS pricing and regional availability change. Verify current availability and hourly pricing in the target region before long-running tests.
