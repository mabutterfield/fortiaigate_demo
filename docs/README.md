# FortiAIGate Demo Documentation

This is the main documentation landing page for the FortiAIGate demo deployment.
Start with one quick start, then use the topic docs for details and recovery.

## Quick Starts

| Goal | Document |
|---|---|
| Guided/scripted setup path | [Automated Quick Start](quickstart-automated.md) |
| Step-by-step operator-run deployment | [Manual Quick Start](quickstart-manual.md) |
| End-to-end reference workflow | [Deployment Runbook](deployment-runbook.md) |

## Core Topics

| Topic | Document |
|---|---|
| Current working baseline | [Current Baseline](current-baseline.md) |
| Architecture overview | [Architecture](architecture.md) |
| AWS infrastructure and instance sizing | [AWS](aws.md) |
| ECR repositories and image publishing | [ECR](ecr.md) |
| Kubernetes and k3s operations | [Kubernetes](kubernetes.md) |
| MCP demo tools | [MCP](mcp.md) |
| Helm chart deployment and post-rendering | [Helm](helm.md) |
| Bedrock provider setup and IAM credentials | [Bedrock](bedrock.md) |
| Optional FortiGate appliance | [FortiGate](fortigate.md) |
| Optional FortiWeb appliance | [FortiWeb](fortiweb.md) |
| Ollama provider notes | [Ollama](ollama.md) |
| Common failures and recovery paths | [Troubleshooting](troubleshooting.md) |

## FortiAIGate Setup

| Document | Purpose |
|---|---|
| [FortiAIGate Initial Config](FortiAIGate-initial-config.MD) | First GUI login, AI flow, guard, deploy, and lab API-key setup |
| [AWS k3s Foundation](aws-k3s-foundation.md) | Detailed AWS k3s architecture, host bootstrap behavior, and FortiAIGate deployment mechanics |
| [AWS Instance Sizing](aws_instance.MD) | GPU instance sizing guidance |
| [Terraform Reference](terraform.md) | Terraform module usage, generated Ansible files, and import commands |

## Playbook Intent

- `publish_images.yml`: publishes FortiAIGate release images to ECR.
- `publish_chatbot_images.yml`: builds and publishes the demo chatbot image.
- `bootstrap_gpu_k3s.yml`: configures the GPU host, k3s, NVIDIA runtime, and ingress foundation.
- `validate_k3s.yml`: validates the Kubernetes foundation and prints `GO` or `NO GO`.
- `deploy_fortiaigate.yml`: submits the FortiAIGate Helm release.
- `status_fortiaigate.yml`: gives a simple FortiAIGate `READY`, `NOT READY`, or `ERROR` answer plus the login URL.
- `validate_faig.yml`: performs deeper FortiAIGate checks after status is ready.
- `deploy_litellm.yml`, `deploy_chatbots.yml`, and `deploy_demo_home.yml`: deploy the default demo application layer.
- `deploy_openwebui.yml`: optionally deploys Open WebUI when `openwebui_enabled=true`.
- `deploy_mcp.yml`, `status_mcp.yml`, and `validate_mcp.yml`: deploy and test the optional MCP demo tool server.
- `deploy_demo_https_gateway.yml`: optionally adds self-signed HTTPS listeners for HTTP-only demo services.
- `show_demo_outputs.yml`: prints the Bedrock and LiteLLM provider values needed for FortiAIGate GUI setup.
- `test_litellm_direct.yml`: sends a direct chat completion through LiteLLM for model/profile and prompt-injection checks; set `litellm_direct_test_poll_all_endpoints=true` to test all configured LiteLLM aliases.
- `test_fortiaigate_chat.yml`: sends a FortiAIGate chat completion smoke test; set `fortiaigate_test_poll_all_endpoints=true` to test the configured FAIG route matrix.
- `test_mcp.yml`: sends one sample tool call to the MCP demo tool server.

Internal build notes, experiments, and progress notes should live outside this Git repo in the parent FAIG workspace.
