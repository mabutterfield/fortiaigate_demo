# FortiAIGate Lab Deployment

Infrastructure-as-code for deploying a FortiAIGate demo on AWS GPU instances
and supported local Ubuntu GPU lab hosts.

The repo uses Terraform for AWS infrastructure, Ansible for host and Kubernetes configuration, k3s for single-node orchestration, and Helm for FortiAIGate and demo application deployment.

## Goals

- Deploy FortiAIGate consistently with minimal manual steps
- Support AWS EC2 GPU labs as the default path and local Ubuntu 24.04 GPU labs
  as a supported operator-owned hardware path
- Keep FortiAIGate charts, release images, licenses, and generated credentials outside Git
- Publish release images to private ECR with immutable tags
- Preserve paths for Bedrock, local Ollama, LiteLLM, OpenWebUI, custom chatbot
  demos, and appliance-fronted routing

## Current Status

- AWS EC2 single-node k3s deployment is implemented
- NVIDIA driver, container runtime, RuntimeClass, and device plugin are automated
- Private ECR repository creation and image publishing are implemented
- FortiAIGate Helm deployment uses external release charts and post-render patches
- LiteLLM, MCP demo tools, custom chatbot, HTTPS gateway, and demo home deployment roles are implemented for the agent demo path
- Open WebUI is available as an optional secondary chat UI when enabled
- MCP demo tools and chatbot tool-loop support are implemented, including deterministic ordering-demo tools, synthetic HR tools, and read-only FortiGate tool schemas
- Scenario profiles package repeatable demo instructions, MCP tool expectations, and prompt examples while keeping local instruction slots editable
- FortiGate and FortiWeb Terraform plus Ansible appliance baselines are enabled
  by default for the full AWS demo and can be disabled with local overrides
- Local Ubuntu mode is implemented through generated ignored inventory and vars,
  local/LAN registry settings, in-cluster Ollama, GPU UUID mapping, and optional
  local FortiGate/FortiWeb onboarding
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
  -> AWS default provider path: Amazon Bedrock through LiteLLM
  -> local provider path: Ollama in k3s through LiteLLM
  -> appliance paths: FortiGate baseline objects/read-only MCP tools, FortiWeb reverse-proxy NodePorts
```

## v1.0 Supported Paths

| Path | Support level | Notes |
|---|---|---|
| AWS quickstart | Primary supported path | EC2 GPU host, k3s, FortiAIGate, LiteLLM to Bedrock, chatbot, MCP, demo home, optional Open WebUI/HTTPS gateway, FortiGate/FortiWeb enabled by default |
| Local Ubuntu quickstart | Supported lab path | Existing Ubuntu 24.04 GPU host, local/LAN registry, generated local inventory, in-cluster Ollama, optional local FortiGate/FortiWeb onboarding |
| Manual quickstart | Troubleshooting/recovery path | Same components as quickstart, run step by step when the guided script is not the right tool |

FortiAIGate provider, flow, route, and guard setup in the GUI is still manual
for v1.0. Scenario content is synthetic repeatable demo material, not
production policy guidance.

## Choose Your Path

| Goal | Start Here |
|---|---|
| Run the default AWS demo | [Automated Quick Start](docs/quickstart-automated.md) |
| Run on local Ubuntu hardware | [Automated Quick Start - Local Hardware Mode](docs/quickstart-automated.md#local-hardware-mode) |
| Recover or inspect each step manually | [Manual Quick Start](docs/quickstart-manual.md) |
| Understand the full deployment | [Full Documentation](docs/README.md) |

Tracked inventory shortcuts are available at the repo root:

```bash
ansible-playbook -i local ansible/playbooks/status_demo_home.yml
ansible-playbook -i cloud ansible/playbooks/status_demo_home.yml
```

`local` and `cloud` are symlinks to ignored generated inventories. Git stores
only the symlink paths; the generated inventory contents remain local.

## Roadmap

- Harden the v1.0 AWS and local validation matrix
- Add a local-safe long-running traffic generator for demo recordings
- Expand FortiGate/FortiWeb traffic-path policies after the baseline
- Move Terraform state to a remote backend when the workflow leaves local lab mode
- Automate FortiAIGate provider setup when a supported API is identified
- Add cleanup and recovery runbooks for failed Helm releases and license resets
- Evaluate custom AMI support to shorten AWS rebuilds

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
