# Current Baseline

This page is the compact status reference for current defaults. For the design
and request paths, see [Architecture](architecture.md).

## Component Inventory

| Component | Status | Namespace | Default public access |
|---|---:|---|---|
| FortiAIGate | working | `fortiaigate` | `https://<k3s-ip>/ui/` for 8.0.1 |
| LiteLLM | working | `litellm` | `http://<k3s-ip>:30083/ui/` |
| custom chatbot UI | working | `chatbot` | `http://<k3s-ip>:30081` and `https://<k3s-ip>:30444` after HTTPS gateway deploy |
| MCP demo tools | enabled by default, includes customer/ticket/menu/HR/document and read-only FortiGate tool schemas | `mcp` | `http://<k3s-ip>:30084/tools` and `https://<k3s-ip>:30447/tools` after HTTPS gateway deploy |
| FortiAIGate syslog collector | optional log preservation path when the AWS prep syslog bucket exists | `fortiaigate-logging` | internal UDP/514 ClusterIP service |
| demo home | working | `demo-home` | `http://<k3s-ip>:30082` and `https://<k3s-ip>:30445` after HTTPS gateway deploy |
| HTTPS gateway | enabled in system defaults | `demo-https-gateway` | generated HTTPS ports after the playbook runs |
| Open WebUI | optional, disabled by default | `openwebui` | `http://<k3s-ip>:30080` when enabled |
| FortiGate appliance | Terraform and Ansible baseline, enabled by default | n/a | FortiGate EIP |
| FortiWeb appliance | Terraform and Ansible baseline, enabled by default | n/a | FortiWeb EIP and FortiWeb-fronted NodePorts |
| Ollama | supported for local mode, disabled for AWS defaults | `ollama` | local trusted-lab HTTP NodePort `30085` when deployed |

## Supported v1.0 Paths

| Path | Provider | Infrastructure | Notes |
|---|---|---|---|
| AWS quickstart | Bedrock through LiteLLM | Terraform-created EC2 GPU/k3s, ECR, AWS prep, FortiGate, FortiWeb | Primary supported path. FortiGate and FortiWeb are enabled by default for the full AWS demo and can be disabled with ignored local overrides. |
| Local Ubuntu quickstart | Ollama through LiteLLM | Existing Ubuntu 24.04 GPU host, generated local inventory/vars, local or LAN registry | Supported lab path. Local appliances are optional and are onboarded by `scripts/local_setup.py` when present. |
| Manual quickstart | Same as selected AWS/local path | Operator-run Terraform and Ansible commands | Troubleshooting and recovery path. Automated quickstart remains the normal first-run walkthrough. |

Local mode writes ignored generated files such as
`ansible/inventory/local.generated.ini`,
`ansible/group_vars/local.generated.yml`,
`ansible/group_vars/local.secrets.yml`, and local registry/appliance inventory
files. Do not commit those files or exported local-var archives.

## Default Port Map

Terraform generates these values into `ansible/group_vars/ports.generated.yml`
for AWS. Local setup generates compatible values for local mode when needed.

| Service | HTTP | HTTPS gateway |
|---|---:|---:|
| Open WebUI, when enabled | `30080` | `30443` |
| custom chatbot UI | `30081` | `30444` |
| demo home | `30082` | `30445` |
| LiteLLM Admin/API | `30083` | `30446` |
| MCP demo tools | `30084` | `30447` |
| Ollama, local mode only | `30085` | n/a |

The HTTPS gateway terminates a self-signed certificate and proxies to the HTTP
services. It is enabled in repo system defaults, but interactive quickstart
still asks before running the HTTPS gateway playbook.

## Deploy Order

Automated AWS quickstart and manual AWS deployment use this order:

1. Terraform shared config
2. Terraform ECR
3. Terraform AWS prep
4. Terraform EC2 k3s foundation
5. FortiGate Terraform deployment when enabled
6. FortiWeb Terraform deployment when enabled
7. Ansible collection preflight for appliance collections
8. Image publishing when selected
9. k3s bootstrap
10. FortiAIGate Helm deploy
11. FortiAIGate status check
12. FortiGate status poll and baseline/API account configuration when enabled
13. FortiWeb status poll and baseline reverse-proxy configuration when enabled
14. LiteLLM deploy
15. MCP demo tools deploy
16. FortiAIGate syslog collector deploy/status when the syslog bucket exists
17. Open WebUI deploy when `openwebui_enabled=true`
18. custom chatbot UI deploy
19. demo home deploy
20. HTTPS gateway deploy when run
21. FortiWeb/direct HTTP path validation when FortiWeb is enabled
22. final FortiAIGate status check and consolidated output display

Local quickstart skips Terraform and starts from generated local inventory and
vars:

1. `scripts/local_setup.py` captures the local Ubuntu SSH target, local/LAN
   registry, GPU assignment, Ollama defaults, and optional local appliance
   onboarding.
2. `automated_quickstart.py --local` uses
   `ansible/inventory/local.generated.ini`.
3. k3s bootstrap validates local GPU/runtime visibility.
4. FortiAIGate deploy/status runs against the local host.
5. Ollama deploy/status/validate runs in k3s and LiteLLM points at the
   in-cluster Ollama service.
6. MCP, chatbot, demo home, optional Open WebUI, and optional HTTPS gateway use
   the same application roles as the AWS path.
7. Local FortiGate/FortiWeb status and configuration playbooks run only when
   local appliance inventory exists.

Automated quickstart checks FortiAIGate once after Helm deploy, continues with
the remaining app deployments, then checks FortiAIGate status again at the end.
Use `--faig-status-mode wait` when a run should block until FortiAIGate reports
READY before deploying the remaining demo apps.

## Status And Validation Playbooks

| Component | Status | Validation |
|---|---|---|
| k3s foundation | n/a | `validate_k3s.yml` |
| FortiAIGate | `status_fortiaigate.yml` | `validate_faig.yml` |
| FortiGate | `status_fortigate.yml` | `configure_fortigate.yml` gathers and compares managed objects before applying |
| FortiWeb | `status_fortiweb.yml` | `validate_demo_http_paths.yml` checks direct and FortiWeb paths |
| LiteLLM | `status_litellm.yml` | `validate_litellm.yml` |
| Ollama, local mode | `status_ollama.yml` | `validate_ollama.yml` |
| MCP demo tools | `status_mcp.yml` | `validate_mcp.yml` |
| FortiAIGate syslog collector | `status_fortiaigate_syslog_collector.yml` | `test_fortiaigate_syslog_collector.yml` |
| Open WebUI, when enabled | `status_openwebui.yml` | `validate_openwebui.yml` |
| custom chatbot UI | `status_chatbots.yml` | `validate_chatbots.yml` |
| demo home | `status_demo_home.yml` | `validate_demo_home.yml` |

Smoke-test playbooks:

- `test_model_direct.yml`
- `test_litellm_direct.yml`
- `test_fortiaigate_chat.yml`
- `test_mcp.yml`

## Remaining Caveats

- FortiAIGate GUI provider/guard/route setup is still manual.
- FortiWeb MCP Security policy is not automated because the FortiWeb collection
  does not expose the FortiWeb 8.0.3+ MCP Security object yet.
- Long-running traffic generation for video/demo capture is a Phase 10 work
  item.
- The local path is supported for trusted labs. Local Ollama's NodePort is
  plain HTTP and must not be exposed to untrusted networks.
- Some local Phase 9 flows were validated in the lab and still need the Phase
  10 documented fresh-run validation matrix before v1.0.
- private k3s subnet mode and full appliance-fronted-only access remain future
  validation items.
