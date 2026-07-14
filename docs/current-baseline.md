# Current Baseline

This page freezes the current working baseline. Use it as the short reference
for what the demo deploys today before FortiWeb/FortiGate traffic paths, shared
ECR modes, and local Ubuntu parity.

## Architecture

```text
Operator workstation
  -> Terraform
      -> ECR repositories
      -> AWS prep IAM, EIPs, Bedrock credentials
      -> VPC, subnets, security group, EC2 k3s host
  -> Ansible
      -> optional image publishing
      -> k3s bootstrap
      -> FortiAIGate
      -> LiteLLM
      -> custom chatbot UI
      -> optional Open WebUI
      -> optional MCP demo tools
      -> demo home
      -> optional HTTPS gateway
```

Runtime LLM paths:

```text
Direct path:
Browser UI -> LiteLLM -> Bedrock

FortiAIGate-inspected path:
Browser UI -> FortiAIGate explicit /v1/<flow-name> path -> LiteLLM -> Bedrock
```

Optional chatbot MCP agent path:

```text
Browser
  -> custom chatbot UI
      -> Direct LiteLLM or FortiAIGate -> LiteLLM -> Bedrock
      -> MCP demo tools
      -> Direct LiteLLM or FortiAIGate -> LiteLLM -> Bedrock
```

FortiAIGate must be manually configured to use the in-cluster LiteLLM endpoint
when testing the inspected LiteLLM path.

## Component Inventory

| Component | Status | Namespace | Default public access |
|---|---:|---|---|
| FortiAIGate | working | `fortiaigate` | `https://<k3s-ip>/ui/` for 8.0.1 |
| LiteLLM | working | `litellm` | `http://<k3s-ip>:30083/ui/` |
| Open WebUI | optional, disabled by default | `openwebui` | `http://<k3s-ip>:30080` when enabled |
| custom chatbot UI | working | `chatbot` | `http://<k3s-ip>:30081` |
| MCP demo tools | optional baseline | `mcp` | `http://<k3s-ip>:30084/tools` |
| demo home | working | `demo-home` | `http://<k3s-ip>:30082` |
| HTTPS gateway | optional | `demo-https-gateway` | generated HTTPS ports |
| FortiWeb/FortiGate appliances | deferred | n/a | not implemented |

## Default Port Map

The current no-DNS default is port-based NodePort access. Terraform generates
these values into `ansible/group_vars/ports.generated.yml`.

| Service | HTTP | Optional HTTPS |
|---|---:|---:|
| Open WebUI, when enabled | `30080` | `30443` |
| custom chatbot UI | `30081` | `30444` |
| demo home | `30082` | `30445` |
| LiteLLM Admin/API | `30083` | `30446` |
| MCP demo tools | `30084` | `30447` |

The optional HTTPS gateway terminates a self-signed certificate and proxies to
the HTTP NodePorts. Internal Kubernetes communication remains plain HTTP.

## Deploy Order

Automated quick start and manual deployment use this order:

1. Terraform shared config
2. Terraform ECR
3. Terraform AWS prep
4. Terraform EC2 k3s foundation
5. Optional image publishing
6. k3s bootstrap
7. FortiAIGate deploy
8. FortiAIGate status check
9. LiteLLM deploy
10. optional Open WebUI deploy, skipped unless `openwebui_enabled=true`
11. custom chatbot UI deploy
12. optional MCP demo tools deploy
13. demo home deploy
14. optional HTTPS gateway deploy
15. final FortiAIGate status check
16. consolidated output display

Automated quick start checks FortiAIGate once after Helm deploy, continues with
the remaining app deployments, then checks FortiAIGate status again at the end.
Use `--faig-status-mode wait` when a run should block until FortiAIGate reports
READY before deploying the remaining demo apps.

## Status And Validation Playbooks

| Component | Status | Validation |
|---|---|---|
| k3s foundation | n/a | `validate_k3s.yml` |
| FortiAIGate | `status_fortiaigate.yml` | `validate_faig.yml` |
| LiteLLM | `status_litellm.yml` | `validate_litellm.yml` |
| Open WebUI, when enabled | `status_openwebui.yml` | `validate_openwebui.yml` |
| custom chatbot UI | `status_chatbots.yml` | `validate_chatbots.yml` |
| MCP demo tools | `status_mcp.yml` | `validate_mcp.yml` |
| demo home | `status_demo_home.yml` | `validate_demo_home.yml` |

Smoke-test playbooks:

- `test_model_direct.yml`
- `test_litellm_direct.yml`
- `test_fortiaigate_chat.yml`
- `test_mcp.yml`

## Deferred Work

The following are intentionally not part of the current baseline:

- FortiWeb-protected MCP path
- FortiGate/FortiWeb appliance Terraform deployment
- private k3s mode validation
- shared/cross-account ECR support
- host-based/path-based routing implementation
- local Ubuntu installation workflow
