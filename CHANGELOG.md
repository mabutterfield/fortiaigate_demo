# Changelog

This file summarizes major user-facing changes. It is intentionally written as
a "what's new" guide rather than a raw commit log.

## v0.4 - Phase 4 Appliance Baseline

Release date: 2026-07-14

Adds the optional FortiGate and FortiWeb appliance baseline without moving the
default public k3s/FortiAIGate path to a private or appliance-fronted topology.

### FortiGate And FortiWeb

- Added `terraform/aws-fortigate` for optional FortiGate EC2 deployment.
- Added `terraform/aws-fortiweb` for optional FortiWeb EC2 deployment.
- Added two-ENI appliance layouts:
  - public/management ENI
  - internal ENI
- Added prep-owned FortiGate and FortiWeb EIP support.
- Added FortiGate cloud-init bootstrap for management, SSH, admin timeout, and
  API admin token generation.
- Added FortiWeb S3-backed cloud-init bootstrap with generated config and BYOL
  license object upload.
- Set FortiWeb default version filter to `8.0` and default instance type to
  `c5.xlarge` after validating the FortiWeb Marketplace image constraints.
- Confirmed both FortiGate and FortiWeb initial admin password behavior uses
  the EC2 instance ID when an explicit initial password is not set.

### AWS Prep And Network Layout

- Extended `terraform/aws-prep` with optional appliance EIPs.
- Added FortiWeb cloud-init S3 bucket, bucket public-access blocking,
  encryption, versioning, TLS-only bucket policy, and FortiWeb instance-profile
  read access.
- Added FortiGate and FortiWeb public IP outputs.
- Added dedicated FortiGate and FortiWeb internal subnets and route tables in
  `terraform/aws-ec2-k3s`.
- Split the VPC Mermaid diagram into a compact VPC topology diagram and a
  separate AWS prep/module dependency diagram.

### Automated Upgrade And Repeat Runs

- Added `scripts/upgrade_v0_3_to_v0_4.py` for local ignored config migration
  when upgrading an existing `v0.3` lab.
- Automated quickstart now runs the v0.3-to-v0.4 upgrade step before normal
  example/default syncing.
- The upgrade script:
  - moves legacy module-local `ssh_key_name` into `terraform/common.tfvars`
  - comments out old module-local `ssh_key_name` assignments
  - creates missing FortiGate/FortiWeb local tfvars from examples
  - enables appliance prep defaults when local values still reflect the v0.3
    no-appliance baseline
- Automated quickstart now completes all Terraform, including enabled
  FortiGate/FortiWeb modules, before the k3s readiness wait and Ansible.
- Automated teardown now destroys FortiWeb and FortiGate before destroying the
  k3s foundation and AWS prep resources.
- ECR teardown now removes repositories from state and then runs a full ECR
  module destroy for remaining lifecycle/local-output resources, avoiding
  routine Terraform `-target` warnings.

### Shared Terraform Defaults

- Moved `ssh_key_name` into `terraform/common.tfvars` so k3s, FortiGate, and
  FortiWeb use the same AWS EC2 key pair.
- FortiGate and FortiWeb example tfvars are enabled by default for the Phase 4
  project baseline.
- Local private-key path remains in `terraform/aws-ec2-k3s/terraform.tfvars`
  because it is used for generated Ansible inventory.

### Deferred

- FortiGate private k3s routing/NAT/inspection path.
- FortiWeb-protected MCP or application publishing path.
- Full private `k3s_subnet_mode = "private"` validation.
- Fortinet policy automation and chatbot/MCP-driven Fortinet configuration.
- FortiFlex licensing.

## v0.3 - Phase 3 Demo Milestone

Release date: 2026-07-14

Consolidates the work after `v0.2` into the Phase 3 demo milestone.

Validation note: this release has been exercised through repeated build/rebuild
cycles and targeted component testing. Not every optional configuration path has
been fully retested from a completely fresh environment, including a fully fresh
ECR repository creation/import and image publishing cycle. Treat the documented
default path as the primary validated workflow and use the status/test playbooks
after changing optional paths.

### Agent, LiteLLM, And Chatbot Demo

- Made LiteLLM the baseline model/provider layer for the demo.
- Added LiteLLM profile aliases for:
  - `pass-bedrock`
  - `demo-a`
  - `demo-b`
  - `demo-a-faig-be`
  - `demo-b-faig-be`
- Added backend instruction-profile support through LiteLLM.
- Consolidated the custom chatbot into one UI with selectable paths:
  - direct LiteLLM
  - FortiAIGate static route
  - FortiAIGate intelligent/header route
- Added path-specific profile selectors in the chatbot UI.
- Added optional frontend system-prompt injection for the chatbot.
- Made chatbot image publishing separate from FortiAIGate image publishing.
- Made the chatbot ECR image mutable for faster demo iteration.
- Added source checksum rollout support so chatbot app changes trigger a pod
  rollout on redeploy.

### MCP Demo Tools

- Added an optional MCP demo server in the `mcp` namespace.
- Added deterministic demo tools:
  - customer lookup/search
  - ticket lookup/search
  - policy lookup/search
  - customer ticket summary
  - echo/debug
- Added MCP Ansible playbooks:
  - `deploy_mcp.yml`
  - `status_mcp.yml`
  - `validate_mcp.yml`
  - `test_mcp.yml`
- Added an LLM-directed MCP tool loop to the custom chatbot:
  - the model receives available tool schemas
  - the model requests tool calls
  - the chatbot calls MCP
  - the chatbot sends tool results back through the selected LLM path
- Added configurable MCP direct/FortiWeb-future endpoint variables.

### FortiAIGate Routing And Validation

- Reworked the FortiAIGate routing model around explicit URI paths.
- Documented that broad `/v1/*` fallback routes should be created last.
- Added supported default FAIG route concepts:
  - `/v1/passthrough/*`
  - `/v1/demo-a/*`
  - `/v1/demo-b/*`
  - `/v1/demo-a-faig-be/*`
  - `/v1/demo-b-faig-be/*`
  - `/v1/intelligent/*`
  - fallback `/v1/*`
- Added FAIG intelligent routing defaults using a configurable model-route
  header.
- Updated `test_fortiaigate_chat.yml` to support:
  - single endpoint tests
  - route-matrix tests
  - static routes
  - intelligent/header routes
  - optional diagnostic routes
  - concise final pass/fail summary
- Changed route-matrix behavior to continue after expected endpoint failures
  and report a final summary instead of stopping at the first failed endpoint.
- Updated test prompts so each route asks the model to repeat the URI under
  test, making FortiAIGate logs easier to verify.

### Open WebUI, Demo Home, And HTTPS Gateway

- Consolidated Open WebUI into one optional deployment.
- Changed Open WebUI to default-off so the primary demo path uses the custom
  chatbot UI unless `openwebui_enabled=true`.
- Updated Open WebUI settings for the LiteLLM/FortiAIGate model path when it is
  enabled.
- Updated the demo home page to link to:
  - FortiAIGate Admin UI
  - custom chatbot
  - Open WebUI when enabled
  - LiteLLM Admin UI
  - MCP tools
- Added optional HTTPS gateway support for HTTP-only demo services.
- Aligned generated HTTP and HTTPS NodePort assignments by index:
  - `30080` -> `30443`
  - `30081` -> `30444`
  - `30082` -> `30445`
  - `30083` -> `30446`
  - `30084` -> `30447`
- Updated consolidated demo outputs to print HTTP/HTTPS URLs, LiteLLM provider
  values, and SSH access instructions.

### Automated Setup, Teardown, And Local Config

- Expanded `scripts/automated_quickstart.py` into a fuller guided workflow:
  - prerequisite checks
  - AWS profile/login handling
  - AWS SSO/device-code prompt support
  - CIDR validation and `/32` conversion prompt for bare public IPs
  - EC2 SSH key selection
  - FortiAIGate license preflight
  - LiteLLM key/password prompts
  - ECR state inspection/import guidance
  - Terraform apply across ECR, AWS prep, and EC2 k3s foundation
  - EC2 readiness polling
  - optional image publishing
  - Ansible deployment orchestration
- Added `--yolo` mode for repeat lab rebuilds using preconfigured values.
- Changed automated quickstart to check FortiAIGate status once after deploy,
  continue with the remaining app deployments, then check FortiAIGate status
  again at the end.
- Added `scripts/automated_teardown.py` for repeat lab teardown while
  preserving ECR repositories.
- Added `scripts/backup_config.py` usage to preserve local config, generated
  values, inventory, and Terraform state before destructive work.
- Added `scripts/sync_all_vars.py` and wired it into automated quickstart so
  new example defaults are appended to existing local files without overwriting
  local values.

### Terraform And AWS Infrastructure

- Continued the split Terraform flow:
  - `terraform/common.tfvars`
  - `terraform/aws-ecr`
  - `terraform/aws-prep`
  - `terraform/aws-ec2-k3s`
- Added/continued AWS Prep as the home for:
  - EC2 IAM role/profile
  - ECR pull permissions
  - trusted source CIDRs
  - EIPs
  - optional Bedrock IAM values
- Added generated demo port output for Ansible through
  `ansible/group_vars/ports.generated.yml`.
- Added support for multiple trusted source CIDRs.
- Added EC2 hourly and monthly compute cost outputs using AWS Price List data.
- Added VPC layout documentation for:
  - public k3s subnet
  - private k3s subnet placeholder
  - FortiGate/FortiWeb public subnet placeholders
  - EIPs
  - k3s pod and service networks

### ECR And Image Publishing

- Improved FortiAIGate image publishing idempotency by using source archive
  metadata and skipping already-loaded/published images when possible.
- Added filtering so operators can publish only selected image groups, including
  chatbot-only publishing.
- Documented imported ECR repository teardown safety:
  - remove ECR repo resources from Terraform state before destroy when
    repositories must be preserved
  - keep ECR creation/import as a separate workflow from repeat EC2 rebuilds
- Added future notes for shared, unmanaged, same-account, and cross-account ECR
  use.

### Documentation

- Reworked quickstart documentation into manual and automated flows.
- Added current architecture and baseline docs.
- Added MCP documentation.
- Added VPC layout documentation with Mermaid diagram.
- Rebuilt the FortiAIGate initial configuration guide:
  - LiteLLM provider values
  - guard/provider table
  - route/flow table
  - explicit route order guidance
  - onboarding screenshots
  - guard and flow screenshots
  - intelligent routing screenshots
  - log review guidance
- Added a Mermaid flow reference for the FortiAIGate/LiteLLM/chatbot path.
- Added macOS/Windows/editor noise entries to `.gitignore`.

### Deferred

- FortiWeb and FortiGate appliance deployment.
- Private k3s mode.
- Local Ubuntu parity.
- Bedrock direct as a first-class alternate provider path.
- Ollama as a first-class alternate provider path. Current Ollama support is
  limited to alternate/test configuration after an external Ollama endpoint and
  corresponding provider settings exist.
- Shared/cross-account ECR automation.
- Single smoke-test wrapper script.

## v0.2 - Frontend Redesign

Tag: `v0.2` (`dd84204`)

This was the first larger frontend/application milestone.

- Added the LiteLLM deployment path and Admin UI.
- Added consolidated demo application deployments for:
  - LiteLLM
  - Open WebUI
  - custom chatbot
  - demo home
  - optional HTTPS gateway
- Added chatbot app, Helm chart, and instruction files.
- Added Open WebUI chart/deployment support.
- Added demo home chart/deployment support.
- Added optional HTTPS gateway chart/deployment support.
- Added publish flow for the chatbot image.
- Added status and validation playbooks for the new app layer.
- Added consolidated output playbook for demo URLs and provider values.
- Introduced `terraform/common.tfvars` and moved user-facing AWS prep work into
  `terraform/aws-prep`.
- Removed the standalone user-facing `terraform/aws-bedrock` flow in favor of
  AWS Prep.
- Updated quickstart documentation, deployment runbook, architecture docs, and
  troubleshooting docs around the new frontend/application flow.

## v0.1 - FortiAIGate 8.0.1 And Deployment Hardening

Tag: `v0.1` (`9222e3d`)

This milestone stabilized the original FortiAIGate AWS demo and updated it for
FortiAIGate 8.0.1 behavior.

- Updated defaults and docs for FortiAIGate 8.0.1.
- Documented version-specific behavior:
  - UI path changed to `/ui/`
  - default admin password differences
  - HTTPS backend behavior
  - Triton startup timing
- Added initial FortiAIGate GUI setup screenshots.
- Improved README quickstart and deployment runbook flow.
- Improved k3s validation output with `GO` / `NO GO` style status.
- Improved FortiAIGate status output.
- Added or refined FortiAIGate validation and chat test behavior.
- Improved image publishing by splitting archive load/push behavior and adding
  idempotency checks.
- Moved smoke-test helper scripts under `scripts/`.
- Added Bedrock direct test helper updates.

## Initial Foundation

Commits before `v0.1` established the first working AWS/k3s/FortiAIGate demo
foundation.

- Initial repository structure and README.
- Terraform module for AWS EC2 k3s foundation.
- Terraform module for ECR repositories.
- Initial Bedrock IAM setup.
- Ansible bootstrap for Ubuntu 24.04 GPU k3s host.
- NVIDIA driver/runtime and k3s bootstrap automation.
- FortiAIGate Helm deployment automation.
- Initial deployment docs and troubleshooting notes.
- Instance sizing notes.
- First full successful Terraform + Ansible test pass.
