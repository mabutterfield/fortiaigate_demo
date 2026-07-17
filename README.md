# FortiAIGate Lab Deployment

Infrastructure-as-code for deploying a FortiAIGate demo on AWS GPU instances and, where practical, local Ubuntu GPU hosts.

The repo uses Terraform for AWS infrastructure, Ansible for host and Kubernetes configuration, k3s for single-node orchestration, and Helm for FortiAIGate and demo application deployment.

## Goals

- Deploy FortiAIGate consistently with minimal manual steps
- Support AWS EC2 GPU labs first, then local Ubuntu 24.04 GPU hosts
- Keep FortiAIGate charts, release images, licenses, and generated credentials outside Git
- Publish release images to private ECR with immutable tags
- Preserve paths for Bedrock, Ollama, LiteLLM, OpenWebUI, custom chatbot demos, and appliance-fronted routing

## Current Status

- AWS EC2 single-node k3s deployment is implemented
- NVIDIA driver, container runtime, RuntimeClass, and device plugin are automated
- Private ECR repository creation and image publishing are implemented
- FortiAIGate Helm deployment uses external release charts and post-render patches
- LiteLLM, MCP demo tools, custom chatbot, HTTPS gateway, and demo home deployment roles are implemented for the agent demo path
- Open WebUI is available as an optional secondary chat UI when enabled
- MCP demo tools and chatbot tool-loop support are implemented
- FortiGate and FortiWeb Terraform plus Ansible appliance baselines are enabled
  by default for the full AWS demo and can be disabled with local overrides
- Automated quickstart and teardown scripts support repeat lab rebuilds
- FortiAIGate 8.0.0 and 8.0.1 image/chart version patterns are documented

See [CHANGELOG.md](CHANGELOG.md) for a consolidated "what's new" summary.

## High-Level Architecture

```text
Operator workstation
  -> Terraform: ECR, AWS prep IAM/EIPs, EC2 k3s foundation, appliance EC2s
  -> Ansible: publish images, bootstrap k3s, configure appliances, deploy apps
  -> k3s host: nginx ingress, FortiAIGate, LiteLLM, MCP, chatbot, HTTPS gateway, demo home
  -> optional k3s apps: Open WebUI
  -> default provider path: Amazon Bedrock through LiteLLM
  -> future/manual provider path: Ollama
  -> appliance paths: FortiGate baseline objects, FortiWeb reverse-proxy NodePorts
```

## Choose Your Path

| Goal | Start Here |
|---|---|
| Get running quickly with a script | [Automated Quick Start](docs/quickstart-automated.md) |
| Run each step manually | [Manual Quick Start](docs/quickstart-manual.md) |
| Understand the full deployment | [Full Documentation](docs/README.md) |

## Roadmap

- Add a first-class local Ubuntu GPU host workflow
- Expand FortiGate/FortiWeb traffic-path policies after the baseline
- Move Terraform state to a remote backend when the workflow leaves local lab mode
- Automate FortiAIGate provider setup when a supported API is identified
- Add cleanup and recovery runbooks for failed Helm releases and license resets
- Add first-class Ollama provider setup after the workflow is built

## Repository Layout

```text
terraform/      AWS infrastructure modules
ansible/        Image publishing, host bootstrap, deploy, status, and validation playbooks
helm-values/    Example FortiAIGate Helm values
k8s-overlays/   Helm post-renderer and patch notes
docs/           Quick starts, architecture, operations, and troubleshooting documentation
scripts/        Operational helper scripts
chatbot/        Demo chatbot, LiteLLM, OpenWebUI-adjacent app assets, and home page charts
```
