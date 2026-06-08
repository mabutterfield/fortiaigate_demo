# AWS k3s Foundation Notes

## Scope

Terraform creates a new lab VPC, public subnet, security group, Elastic IP, and a single Ubuntu 24.04 GPU EC2 instance. Ansible prepares the host and deploys FortiAIGate.

IAM role creation is out of scope for phase 1. Supply an existing IAM instance profile that already grants ECR read access.

## Instance Size

The Terraform default is `g4dn.xlarge` to keep infrastructure testing cheaper. The previous working FortiAIGate deployment used `g4dn.4xlarge`; use that override for full application validation.

## Storage

k3s uses AWS g4dn instance-store NVMe for `/var/lib/rancher` when available. The deployment renders the FortiAIGate chart with `local-path` and patches storage to `ReadWriteOnce`, matching the proven single-node k3s path.

## Helm Chart

The FortiAIGate chart is not vendored into this repo. Ansible copies the chart from `fortiaigate_chart_path` to a remote temporary staging directory, stages licenses there, and runs Helm with a post-renderer.

## Required Local Inputs

- `terraform/aws-ec2-k3s/terraform.tfvars`
- `ansible/group_vars/all.yml`
- license files in the configured `license_source_dir`
- an AWS SSO session before Terraform operations

All of these contain environment-specific or sensitive values and are ignored by Git.
