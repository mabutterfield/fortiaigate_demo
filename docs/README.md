# FortiAIGate Demo Documentation

This is the main documentation landing page for the FortiAIGate demo deployment.
Start with one quick start, then use the topic docs for details and recovery.

Status: Phase 11 is the intended v1.0 baseline. Installed scenarios generate
scenario-owned paths and runtime metadata. Phase 10 `demo-a`/`demo-b` names are
compatibility-only and are not part of the default runtime model.

## TLDR Paths

| Operator path | Use when | Start |
|---|---|---|
| AWS quickstart | You want the default supported demo on EC2 GPU, k3s, FortiAIGate, LiteLLM to Bedrock, chatbot, MCP, and appliances | `python3 scripts/automated_quickstart.py` |
| Local hardware quickstart | You have an existing Ubuntu 24.04 GPU host and a reachable local/LAN registry | `python3 scripts/local_setup.py`, then `python3 scripts/automated_quickstart.py --local` |
| Manual recovery | You need to inspect or rerun one Terraform or Ansible step | [Manual Quick Start](quickstart-manual.md) |

The automated AWS quickstart is the primary operator walkthrough. The manual
quickstart is intentionally a step-by-step recovery and troubleshooting
reference, not a competing first-run path.

## Quick Starts

| Goal | Document |
|---|---|
| Default guided AWS setup path | [Automated Quick Start](quickstart-automated.md) |
| Local Ubuntu GPU hardware path | [Automated Quick Start - Local Hardware Mode](quickstart-automated.md#local-hardware-mode) |
| Step-by-step operator-run recovery path | [Manual Quick Start](quickstart-manual.md) |
| End-to-end reference workflow | [Deployment Runbook](deployment-runbook.md) |

## Core Topics

| Topic | Document |
|---|---|
| Current working baseline | [Current Baseline](current-baseline.md) |
| Release validation matrix | [Release Validation Matrix](release-validation-matrix.md) |
| Architecture overview | [Architecture](architecture.md) |
| AWS infrastructure and instance sizing | [AWS](aws.md) |
| ECR repositories and image publishing | [ECR](ecr.md) |
| Kubernetes, k3s, Helm, and post-rendering | [Kubernetes](kubernetes.md) |
| MCP demo tools | [MCP](mcp.md) |
| Scenario installation, generated routes, and demo prompts | [Scenarios](scenarios.md) |
| Scenario catalog and lifecycle status | [Scenario Catalog](scenario-catalog.md) |
| Scenario package authoring and deploy boundaries | [Scenario Authoring](scenario-authoring.md) |
| Scenario creation, tuning, and evidence process | [Scenario Documentation Process](scenario-documentation-process.md) |
| Traffic generator | [Traffic Generator](traffic-generator.md) |
| Phase 8 scenario/model test matrix | [Phase 8 Reference Matrix](phase8-reference-matrix.md) |
| FortiAIGate syslog preservation | [FortiAIGate Syslog Preservation](fortiaigate-syslog-preservation.md) |
| Bedrock provider setup and IAM credentials | [Bedrock](bedrock.md) |
| FortiGate appliance | [FortiGate](fortigate.md) |
| FortiGate traffic demo | [FortiGate Traffic Demo](fortigate-proxy-demo.md) |
| FortiWeb appliance | [FortiWeb](fortiweb.md) |
| Ollama provider notes | [Ollama](ollama.md) |
| Known issues and workarounds | [Known Issues](known-issues.md) |
| Common failures and recovery paths | [Troubleshooting](troubleshooting.md) |

## FortiAIGate Setup

| Document | Purpose |
|---|---|
| [FortiAIGate Initial Config](FortiAIGate-initial-config.MD) | Reusable GUI walkthrough for scenario-generated flows, guards, deploy, and lab API-key setup |
| [FortiAIGate Lab Flows](fortiaigate-lab-flows.md) | Canonical scenario-to-FAIG-to-LiteLLM route diagram |
| [AWS k3s Foundation](aws-k3s-foundation.md) | Detailed AWS k3s architecture, host bootstrap behavior, and FortiAIGate deployment mechanics |
| [AWS Instance Sizing](aws_instance.MD) | GPU instance sizing guidance |
| [AWS NVIDIA Package Cache Workaround](aws-nvidia-package-cache-workaround.md) | Temporary S3 cache workaround for slow NVIDIA package downloads |
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
- `deploy_ollama.yml`, `status_ollama.yml`, and `validate_ollama.yml`: deploy,
  inspect, and test in-cluster Ollama for local hardware mode.
- `deploy_mcp.yml`, `status_mcp.yml`, and `validate_mcp.yml`: deploy and test the MCP demo tool server.
- `deploy_fortiaigate_syslog_collector.yml`, `status_fortiaigate_syslog_collector.yml`, and `test_fortiaigate_syslog_collector.yml`: deploy, inspect, and send a synthetic UDP test message to the FortiAIGate syslog preservation collector.
- `deploy_demo_https_gateway.yml`: adds self-signed HTTPS listeners for HTTP-only demo services when run and enabled.
- `show_demo_outputs.yml`: prints the Bedrock and LiteLLM provider values needed for FortiAIGate GUI setup.
- `test_litellm_direct.yml`: sends a direct chat completion through LiteLLM for model/profile and prompt-injection checks; set `litellm_direct_test_poll_all_endpoints=true` to test all configured LiteLLM aliases.
- `test_fortiaigate_chat.yml`: sends a FortiAIGate chat completion test; set
  `fortiaigate_test_poll_all_endpoints=true` to test the generated, installed
  scenario route matrix plus passthrough.
- `test_fortiaigate_lite.yml`: performs the lightweight generated FAIG route
  test without scenario behavior assertions.
- `test_mcp.yml`: sends one sample tool call to the MCP demo tool server.
- `scripts/scenario_test_harness.py`: runs repeatable Phase 8 scenario/model sweeps through the chatbot-owned MCP agent loop and saves ignored raw output under `docs/raw-output/`.
- `scripts/traffic_generator.py`: runs a default FAIG path test, then supports
  steady or burst chatbot/MCP traffic profiles with compact ignored metadata
  under `docs/raw-output/traffic/`, including an optional FortiGate-to-LiteLLM
  path when `chatbot_fortigate_litellm_base_url` is configured and optional
  FAIG static routes through FortiGate when `chatbot_faig_base_url` points to
  the FortiGate HTTPS listener.
- `scripts/fortigate_ai_app_proxy_touch.py`: touches AI application endpoints
  directly by default, or through a run-scoped FortiGate explicit proxy URL, for
  Application Control log investigation.
- `scripts/export_fortiaigate_syslog.py`: syncs FortiAIGate syslog S3 objects into `FAIG/backups/` and reconstructs a combined JSONL archive.
- `scripts/local_setup.py`: generates ignored local Ubuntu inventory, registry,
  GPU, Ollama, and optional local appliance vars for `--local` deployments.
- `scripts/local_var_cleanup.py`: exports/imports/removes generated local vars
  and inventories without committing them.
- `scripts/smoke_test.py`: release-maintainer no-apply validation; operators do
  not need it for a normal quickstart.

Internal build notes, experiments, and progress notes should live outside this
Git repo in the parent FAIG workspace.
