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
# AWS GPU Instance Candidates for FortiAIGate Testing
FortiAIGate  minimum configuration:
- 4 CPU cores
- 725 GB RAM
- 250 GB NVMe SSD
- Single GPU w/24 GB VRAM
- Supported NVIDIA GPU: L4, A10, A100


FortiAIGate recommended configuration:
- 24 CPU cores
- 70 GB RAM
- 250 GB NVMe SSD
- Single GPU w/24 GB VRAM
- Supported NVIDIA GPU: L4, A10, A100


---

## Cheapest / Not Officially Supported (T4)

| Instance | GPU | GPU Count | Total GPU RAM | vCPU | RAM | Local NVMe | Approx Cost (us-east-1) | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| g4dn.xlarge | Tesla T4 | 1 | 16 GB | 4 | 16 GB | 125 GB | ~$0.53/hr | Kubernetes smoke test only |
| g4dn.2xlarge | Tesla T4 | 1 | 16 GB | 8 | 32 GB | 225 GB | ~$0.75/hr | Meets minimum deployment requirements |
| g4dn.8xlarge | Tesla T4 | 1 | 16 GB | 32 | 128 GB | 900 GB | ~$2.18/hr | Meets recommended CPU/RAM/NVMe; T4 not officially supported |

---

## Reasonable Lab Environment

| Instance | GPU | GPU Count | Total GPU RAM | vCPU | RAM | Local NVMe | Approx Cost (us-east-1) | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| g6.4xlarge | NVIDIA L4 | 1 | 24 GB | 16 | 64 GB | 600 GB | ~$1.32/hr | Strong general-purpose lab candidate |

---

## Recommended / Production-Like Testing

| Instance | GPU | GPU Count | Total GPU RAM | vCPU | RAM | Local NVMe | Approx Cost (us-east-1) | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| g5.8xlarge | NVIDIA A10G | 1 | 24 GB | 32 | 128 GB | 900 GB | ~$2.45/hr | Meets recommended CPU/RAM  |
| g5.12xlarge | NVIDIA A10G | 4 | 96 GB | 48 | 192 GB | 3,800 GB | ~$5.67/hr | Meets all recommendations including multi-GPU |
| g6.8xlarge | NVIDIA L4 | 1 | 24 GB | 32 | 128 GB | 900 GB | ~$2.01/hr | Meets recommended CPU/RAM; likely best value |
| g6.12xlarge | NVIDIA L4 | 4 | 96 GB | 48 | 192 GB | 3,800 GB | ~$4.03/hr | Meets all recommendations including multi-GPU |

---

## Interesting Tests

These are not currently prioritized, but are compelling due to large amounts of VRAM per GPU.

| Instance | GPU | GPU Count | Total GPU RAM | vCPU | RAM | Local NVMe | Approx Cost (us-east-1) | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| g6e.4xlarge | NVIDIA L40S | 1 | 48 GB | 16 | 128 GB | 940 GB | ~$3.80/hr | Large single-GPU VRAM; may eliminate need for multi-GPU |
| g7e.4xlarge | NVIDIA RTX PRO 6000 Blackwell | 1 | 96 GB | 16 | 128 GB | 940 GB | ~$4.00/hr | Extremely large VRAM; future-looking evaluation target |

---

## Summary

### Automation test only

text g4dn.xlarge 

### Lowest Cost Functional Deployment

text g4dn.2xlarge 

### Best Value T4 Deployment

text g4dn.8xlarge 

### Best Overall Lab Candidate

text g6.4xlarge 

### Best Production-Like Single GPU Candidate

text g6.8xlarge 

### Best Production-Like Multi-GPU Candidate

text g6.12xlarge 