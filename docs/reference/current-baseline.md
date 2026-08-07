# Current Baseline

This is the authoritative status reference for the FortiAIGate demo v1.0
baseline. It distinguishes what is enabled by default from what is optional,
validated, candidate, or deferred. For request flows and component
relationships, see [Architecture](../architecture.md).

## Support Vocabulary

| Term | Meaning |
|---|---|
| Default | Selected or deployed by the normal quickstart when prerequisites are available |
| Optional | Supported but not required for the core deployment |
| Configurable | Behavior an operator can change through documented local overrides |
| Validated | Exercised successfully as part of the current scenario baseline |
| Candidate | Retained for future work but not presented as a working scenario |
| Deferred | Deliberately outside the supported baseline |

## Feature And Support Matrix

| Feature | Classification | Current behavior |
|---|---|---|
| AWS EC2 GPU deployment | Default, validated | Primary lane; Terraform builds infrastructure and LiteLLM uses Bedrock |
| Local Ubuntu 24.04 GPU deployment | Optional, validated | Supported lab lane; environment-owned generated inventory replaces Terraform and LiteLLM uses in-cluster Ollama |
| FortiAIGate, LiteLLM, custom chatbot, MCP, Demo Home | Default | Core k3s application layer |
| FortiGate appliance | Default when prerequisites exist; optional to the core | Desired by quickstart with an explicit opt-out; missing prerequisites produce a safe skip |
| FortiWeb appliance | Default when prerequisites exist; optional to the core | Desired by quickstart with an explicit opt-out; missing prerequisites produce a safe skip |
| FortiWeb MCP transport | Default when FortiWeb is installed and desired | Preferred MCP route; falls back to Direct MCP with a warning |
| Direct MCP transport | Default fallback | Used when the FortiWeb route is unavailable or explicitly disabled |
| HTTPS gateway | Default, configurable | Self-signed HTTPS NodePorts; the operator can skip the playbook or provide certificate overrides |
| FortiAIGate syslog preservation | Optional, configurable | Stop-gap log preservation when FortiAnalyzer is unavailable; it is not a FortiAnalyzer replacement |
| Open WebUI | Optional, disabled, unconfigured | Deployment capability for future or custom use; no supported scenario/provider configuration or validation is supplied |
| FAIG re-entry chain | Available, configurable, scenario-disabled | Global topology is enabled; every built-in scenario opts out by default |
| Functional scenario validation | Validated | `python3 -m functional_test` reads installed scenario metadata and verifies expected Alert, Deny, and Redact behavior |
| Dashboard load generation | Developer-only | Optional `load_test` workload; not part of setup or functional acceptance |
| FortiGate LLM and appliance-fronted FAIG traffic | Deferred | Configuration experiments remain available, but these are disabled and not baseline paths |

## Scenario Authority

The [Scenario Catalog](../scenario-catalog.md) owns the validated scenario
matrix, security stories, supported actions, aliases, MCP defaults, candidates,
and archived state. This baseline intentionally does not duplicate that list.

All installed scenarios follow the same runtime contract: canonical FAIG
routes use `/v1/<scenario>/<action>/*`, guard names use
`<scenario>_<action>`, and the testing-only bypass is
`/v1/passthrough/*` with the LiteLLM `pass-model` alias.

## Runtime Components And Ports

| Component | Namespace | Default external access |
|---|---|---|
| FortiAIGate 8.x | `fortiaigate` | `https://<k3s-ip>/ui/` |
| LiteLLM | `litellm` | `http://<k3s-ip>:30083/ui/` |
| custom chatbot | `chatbot` | HTTP `30081`; HTTPS `30444` after gateway deploy |
| MCP demo tools | `mcp` | HTTP `30084`; HTTPS `30447` after gateway deploy |
| Demo Home | `demo-home` | HTTP `30082`; HTTPS `30445` after gateway deploy |
| Open WebUI, when enabled | `openwebui` | HTTP `30080`; HTTPS `30443` after gateway deploy |
| Ollama, local mode | `ollama` | trusted-lab HTTP `30085` |
| FAIG syslog collector, when configured | `fortiaigate-logging` | internal UDP/514 only |

Terraform writes AWS port values to
`ansible/group_vars/ports.generated.yml`. Local setup produces compatible
values. The HTTPS gateway terminates a self-signed certificate and proxies to
the internal HTTP services.

## Deployment Lanes

| Lane | Provider | Infrastructure | Support statement |
|---|---|---|---|
| AWS quickstart | Bedrock through LiteLLM | Terraform-created EC2 GPU/k3s, ECR, AWS prep, and desired appliances | Primary supported path |
| Local quickstart | Ollama through LiteLLM | Existing Ubuntu GPU host, local/LAN registry, generated inventory excluded from Git, and optional existing appliances | Supported trusted-lab path |

Both lanes use the automated quickstart. Individual Terraform and Ansible
commands are documented only for operations, inspection, and recovery.

Generated inventories, local variables, license files, credentials, Terraform
state, and installed scenario packages are local state and must not be
committed.

## Validation Entry Points

| Scope | Command or document |
|---|---|
| Installed scenario behavior | `python3 -m functional_test` |
| Scenario metadata | `python3 scripts/scenario_profiles.py validate` |
| Release no-apply and live checks | [Release Validation Matrix](../release-validation-matrix.md) |
| Component status and recovery | [Troubleshooting](../troubleshooting.md) |

## Known Boundaries

- FortiAIGate provider, guard, flow, route, deployment, and lab API-key setup
  still require the GUI.
- Scenario commands generate an exact FAIG work order but do not create or
  delete GUI objects.
- Tracked scenario examples are read-only templates. Installed scenarios are
  operator-owned local copies excluded by `.gitignore`; updating a template
  requires an explicit reinstall or overwrite workflow so local instruction
  tuning is not silently replaced.
- FortiWeb MCP Security policy automation is unavailable through the current
  collection, so the supported FortiWeb role is transport/reverse proxy.
- Local NodePorts are for trusted labs and must not be exposed to untrusted
  networks.
- Private-k3s-subnet and appliance-fronted-only deployments require additional
  validation.
