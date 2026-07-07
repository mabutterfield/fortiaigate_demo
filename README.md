# FortiAIGate Lab Deployment

Infrastructure-as-code for deploying a FortiAIGate demo on AWS GPU instances and, where practical, local Ubuntu GPU hosts.

The repo uses Terraform for AWS infrastructure, Ansible for host and Kubernetes configuration, k3s for single-node orchestration, and Helm for FortiAIGate and demo application deployment.

## Goals

- Deploy FortiAIGate consistently with minimal manual steps
- Support AWS EC2 GPU labs first, then local Ubuntu 24.04 GPU hosts
- Keep FortiAIGate charts, release images, licenses, and generated credentials outside Git
- Publish release images to private ECR with immutable tags
- Preserve paths for Bedrock, Ollama, LiteLLM, OpenWebUI, custom chatbot demos, and future appliance-fronted routing

## Current Status

- AWS EC2 single-node k3s deployment is implemented
- NVIDIA driver, container runtime, RuntimeClass, and device plugin are automated
- Private ECR repository creation and image publishing are implemented
- FortiAIGate Helm deployment uses external release charts and post-render patches
- LiteLLM, OpenWebUI, custom chatbot, and demo home deployment roles are implemented for the agent demo path
- FortiAIGate 8.0.0 and 8.0.1 image/chart version patterns are documented

## High-Level Architecture

```text
Operator workstation
  -> Terraform: ECR, AWS prep IAM/EIPs, EC2 k3s foundation
  -> Ansible: publish images, bootstrap k3s, deploy FortiAIGate and demo apps
  -> k3s host: nginx ingress, FortiAIGate, LiteLLM, OpenWebUI, chatbot, demo home
  -> Optional providers: Amazon Bedrock, Ollama, future FortiWeb/FortiGate front ends
```

## Choose Your Path

| Goal | Start Here |
|---|---|
| Get running quickly with a script | [Automated Quick Start](docs/quickstart-automated.md) |
| Run each step manually | [Manual Quick Start](docs/quickstart-manual.md) |
| Understand the full deployment | [Full Documentation](docs/README.md) |

## Roadmap

- Add a first-class local Ubuntu GPU host workflow
- Extend the automated bootstrap/setup script beyond Terraform into image publishing, k3s bootstrap, and application deployment
- Expand Terraform support for FortiGate and FortiWeb front ends
- Add MCP server and agent tool-loop demos
- Move Terraform state to a remote backend when the workflow leaves local lab mode
- Automate FortiAIGate provider setup when a supported API is identified
- Add cleanup and recovery runbooks for failed Helm releases and license resets

## Repository Layout

```text
terraform/      AWS infrastructure modules
ansible/        Image publishing, host bootstrap, deploy, status, and validation playbooks
helm-values/    Example FortiAIGate Helm values
k8s-overlays/   Helm post-renderer and patch notes
docs/           Quick starts, architecture, operations, and troubleshooting documentation
scripts/        Operational helper and smoke-test scripts
chatbot/        Demo chatbot, LiteLLM, OpenWebUI-adjacent app assets, and home page charts
```
