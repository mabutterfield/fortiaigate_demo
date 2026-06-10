# AWS k3s Foundation Notes

## Scope

Terraform creates a new lab VPC, public subnet, security group, Elastic IP, and a single Ubuntu 24.04 GPU EC2 instance. Ansible prepares the host and deploys FortiAIGate.

IAM role creation is out of scope for phase 1. Supply an existing IAM instance profile that already grants ECR read access.

## Instance Size

The Terraform default is `g4dn.xlarge` to keep infrastructure testing cheaper. The previous working FortiAIGate deployment used `g4dn.4xlarge`; use that override for full application validation.

## Storage

k3s uses AWS g4dn instance-store NVMe for `/var/lib/rancher` when available. The deployment renders the FortiAIGate chart with `local-path` and patches storage to `ReadWriteOnce`, matching the proven single-node k3s path.

## Helm Chart

The FortiAIGate chart is not vendored into this repo. Store release charts as `FAIG_helm/<version>/fortiaigate`, set `fortiaigate_chart_path` to that extracted chart directory, and keep the vendor `.tgz` beside it if desired. Ansible copies the extracted chart to a remote temporary staging directory, stages licenses there, and runs Helm with a post-renderer.

## Required Local Inputs

- `terraform/aws-ec2-k3s/terraform.tfvars`
- `ansible/group_vars/all.yml`
- license files in the configured `license_source_dir`
- an AWS SSO session before Terraform operations

All of these contain environment-specific or sensitive values and are ignored by Git.


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
| g4dn.xlarge | Tesla T4 | 1 | 16 GB | 4 | 16 GB | 125 GB | ~$0.53/hr | Automation/Kubernetes smoke test only |
| g4dn.2xlarge | Tesla T4 | 1 | 16 GB | 8 | 32 GB | 225 GB | ~$0.75/hr | Meets minimum deployment requirements; requires custom Kubernetes resource limits |
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

### Lowest Cost Functional Deployment (requires modifying Kubernetes limits)

text g4dn.2xlarge

### Best Value T4 Deployment

text g4dn.8xlarge

### Best Overall Lab Candidate

text g6.4xlarge

### Best Production-Like Single GPU Candidate

text g6.8xlarge

### Best Production-Like Multi-GPU Candidate

text g6.12xlarge
