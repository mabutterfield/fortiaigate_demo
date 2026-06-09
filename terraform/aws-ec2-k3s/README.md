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

---
## Instance Sizing notes

| Instance | GPU Type | GPU Count | GPU VRAM | vCPU | RAM | Local NVMe | Approx $/hr us-east-1 | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| g4dn.xlarge | NVIDIA T4 | 1 | 16 GiB | 4 | 16 GiB | 125 GB | $0.5260 | Smoke test only; works but T4 not officially supported |
| g4dn.2xlarge | NVIDIA T4 | 1 | 16 GiB | 8 | 32 GiB | 225 GB | $0.7520 | Meets minimum CPU/RAM; still T4 |
| g4dn.4xlarge | NVIDIA T4 | 1 | 16 GiB | 16 | 64 GiB | 225 GB | $1.2040 | Better lab baseline; still below recommended RAM if recommendation is 128 GB |
| g4dn.8xlarge | NVIDIA T4 | 1 | 16 GiB | 32 | 128 GiB | 900 GB | $2.1760 | Meets recommended CPU/RAM; still only 1 T4 |
| g6.xlarge | NVIDIA L4 | 1 | 24 GiB | 4 | 16 GiB | 250 GB | $0.8048 | Cheapest L4 smoke test; CPU/RAM too small |
| g6.2xlarge | NVIDIA L4 | 1 | 24 GiB | 8 | 32 GiB | 450 GB | $0.9776 | L4 minimum-ish test |
| g6.4xlarge | NVIDIA L4 | 1 | 24 GiB | 16 | 64 GiB | 600 GB | $1.3230 | Strong candidate: supported-class GPU, sane cost |
| g6.8xlarge | NVIDIA L4 | 1 | 24 GiB | 32 | 128 GiB | 900 GB | $2.0144 | Recommended CPU/RAM with L4; cheaper than g4dn.8xlarge |
| g5.xlarge | NVIDIA A10G | 1 | 24 GiB | 4 | 16 GiB | 250 GB | $1.0060 | A10-class smoke test; CPU/RAM too small |
| g5.2xlarge | NVIDIA A10G | 1 | 24 GiB | 8 | 32 GiB | 450 GB | ~$1.2120 | A10 minimum-ish test |
| g5.4xlarge | NVIDIA A10G | 1 | 24 GiB | 16 | 64 GiB | 600 GB | $1.6240 | Good comparison against g6.4xlarge |
| g5.8xlarge | NVIDIA A10G | 1 | 24 GiB | 32 | 128 GiB | 900 GB | $2.4480 | Recommended CPU/RAM with A10G |
| p4d.24xlarge | NVIDIA A100 | 8 | 8 × 40 GiB | 96 | 1152 GiB | 8 TB | $21.9576 | Massive overkill; useful as official A100 comparison |
| p4de.24xlarge | NVIDIA A100 | 8 | 8 × 80 GiB | 96 | 1152 GiB | 8 TB | $27.4471 | Even more overkill; A100 80 GB comparison |