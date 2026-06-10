# AWS EC2 k3s Terraform Module

This module creates the phase 1 AWS lab infrastructure:

- dedicated VPC and public subnet
- internet gateway and public route table
- security group allowing SSH/HTTP/HTTPS from `allowed_ingress_cidr`
- Ubuntu 24.04 GPU EC2 instance
- Elastic IP
- generated Ansible inventory

## IAM

IAM role creation is intentionally out of scope. Provide an existing instance profile through `iam_instance_profile_name`. The attached role must be able to pull from ECR, for example with `AmazonEC2ContainerRegistryReadOnly`.

## Usage

```bash
cp terraform.tfvars.example terraform.tfvars
aws sso login --profile <profile-name>
terraform init
terraform fmt
terraform validate
terraform apply
```

The generated inventory is written to `../../ansible/inventory/aws.generated.ini`.
