# FortiAIGate Lab Deployment

Infrastructure-as-code for deploying a FortiAIGate lab on AWS GPU instances and, where practical, local Ubuntu GPU hosts.

This repository provides a repeatable deployment process using:

- Terraform for AWS infrastructure and private ECR repositories
- Ansible for image publishing, host bootstrap, Kubernetes setup, and deployment
- k3s for single-node Kubernetes orchestration
- Helm plus a post-renderer for FortiAIGate deployment
- Amazon ECR or a local registry for FortiAIGate container images

## Goals

- Deploy FortiAIGate consistently with minimal manual steps
- Support AWS EC2 GPU labs first, then local Ubuntu 24.04 GPU hosts
- Keep FortiAIGate charts and release images outside this repo
- Publish release images to private ECR with immutable tags
- Keep secrets, licenses, kubeconfigs, and generated values out of Git
- Preserve a path for future Ollama, Bedrock, and other provider integrations

## Current Status

- AWS EC2 single-node k3s deployment is implemented
- NVIDIA driver, container runtime, RuntimeClass, and device plugin are automated
- nginx ingress replaces the default k3s Traefik path
- Private ECR repository creation and image publishing are implemented
- FortiAIGate Helm deployment uses external release charts and post-render patches
- FortiAIGate 8.0.0 and 8.0.1 image/chart version patterns are documented

## To-Do

- Add a first-class local Ubuntu GPU host workflow
- Add optional Terraform support for IAM role creation
- Move Terraform state to a remote backend when the workflow leaves phase 1
- Automate FortiAIGate provider setup when a supported API is identified
- Add more deployment validation around FortiAIGate application readiness
- Add cleanup and recovery runbooks for failed Helm releases and license resets

## Repository Layout

```text
terraform/      AWS infrastructure modules
ansible/        Image publishing, host bootstrap, deploy, status, and validation playbooks
helm-values/    Example FortiAIGate Helm values
k8s-overlays/   Helm post-renderer and patch notes
docs/           Deployment, ECR, Terraform, and architecture documentation
scripts/        Reserved for future helper scripts
```

## Prerequisites

- macOS or Linux workstation
- AWS CLI configured for IAM Identity Center / SSO
- Terraform
- Ansible
- Docker
- Helm
- kubectl
- SSH key pair already present in AWS
- Existing EC2 IAM instance profile with ECR read permissions
- FortiAIGate release image archives outside this repo
- FortiAIGate Helm chart extracted outside this repo
- FortiAIGate license files outside this repo

Never commit real `terraform.tfvars`, Ansible secret vars, license files, private keys, kubeconfigs, certificates, API tokens, or generated credentials.

## Quick Start

Authenticate to AWS:

```bash
aws sso login --profile <profile-name>
```

Create or import private ECR repositories:

```bash
cd terraform/aws-ecr
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

Publish FortiAIGate release images:

```bash
cd ../../ansible
cp group_vars/images.example.yml group_vars/images.yml
ansible-playbook playbooks/publish_images.yml
```

Deploy AWS infrastructure:

```bash
cd ../terraform/aws-ec2-k3s
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

Configure deployment variables:

```bash
cd ../../ansible
cp group_vars/all.example.yml group_vars/all.yml
```

Set local values in `group_vars/all.yml`, especially:

- AWS profile/region/account values when not supplied by generated vars
- `fortiaigate_version`
- `fortiaigate_chart_path`
- license source path and license file list
- Ollama endpoint/model if used for validation

Expected chart layout:

```text
FAIG_helm/
  8.0.0/
    FAIG_helm_chart-V8.0.0-build0024-FORTINET.tar.gz
    fortiaigate/
      Chart.yaml
  8.0.1/
    FAIG_helm_chart-V8.0.1-build0031-FORTINET.tar.gz
    fortiaigate/
      Chart.yaml
```

Bootstrap k3s and deploy FortiAIGate:

```bash
ansible-playbook playbooks/bootstrap_gpu_k3s.yml
ansible-playbook playbooks/validate_k3s.yml
ansible-playbook playbooks/deploy_fortiaigate.yml
ansible-playbook playbooks/status_fortiaigate.yml
ansible-playbook playbooks/validate_faig.yml
```

The default network layout avoids overlap between the AWS VPC and k3s internals: AWS VPC `10.20.0.0/16`, k3s pods `10.60.0.0/16`, and k3s services `10.70.0.0/16`. Override these in `terraform/aws-ec2-k3s/terraform.tfvars` before creating the host if they conflict with your environment.

## Documentation

| Document | Purpose |
|---|---|
| [docs/README.md](docs/README.md) | Documentation index |
| [docs/deployment-runbook.md](docs/deployment-runbook.md) | End-to-end deployment workflow |
| [docs/ECR.md](docs/ECR.md) | ECR repository and image publishing workflow |
| [docs/terraform.md](docs/terraform.md) | Terraform module usage and import notes |
| [docs/aws-k3s-foundation.md](docs/aws-k3s-foundation.md) | AWS k3s architecture and implementation notes |
| [k8s-overlays/fortiaigate/README.md](k8s-overlays/fortiaigate/README.md) | Helm post-render patch behavior |

## Operating Notes

Run `bootstrap_gpu_k3s.yml` before `deploy_fortiaigate.yml`. The deploy playbook expects `/etc/rancher/k3s/k3s.yaml` to exist on the target host.

Bootstrap runs the same k3s sanity checks as `validate_k3s.yml` before it completes. The standalone playbook is useful after rebuilds, network changes, or manual troubleshooting.

`terraform/aws-ec2-k3s` writes `ansible/inventory/aws.generated.ini`. `terraform/aws-ecr` writes `ansible/group_vars/ecr.generated.yml`. Both generated files are ignored by Git.

By default, `deploy_fortiaigate.yml` submits the Helm release and returns after Helm accepts the install or upgrade. It does not wait for every pod to become Ready. Use `status_fortiaigate.yml` to monitor pods, PVCs, ingress, Helm release state, and recent events.

After bootstrap, the SSH user has passwordless sudo, `/home/<user>/.kube/config`, and shell profile configuration so interactive `kubectl` works without `sudo` on the k3s host.

FortiAIGate licenses bind to instance identity and may require time to reset after repeated destroy/redeploy cycles. Keep licenses outside this repo and use `fortiaigate_license_files` for single-node labs unless an explicit node-to-license map is required.

## Branching

Do not work directly on `main`. Use feature branches such as:

```text
feat/<topic>
lab/<topic>
bugfix/<topic>
```
