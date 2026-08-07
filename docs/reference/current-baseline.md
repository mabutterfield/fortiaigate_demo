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
| Local Ubuntu 24.04 GPU deployment | Optional, validated | Supported lab lane; generated ignored inventory replaces Terraform and LiteLLM uses in-cluster Ollama |
| FortiAIGate, LiteLLM, custom chatbot, MCP, Demo Home | Default | Core k3s application layer |
| FortiGate appliance | Default when prerequisites exist; optional to the core | Desired by quickstart with an explicit opt-out; missing prerequisites produce a safe skip |
| FortiWeb appliance | Default when prerequisites exist; optional to the core | Desired by quickstart with an explicit opt-out; missing prerequisites produce a safe skip |
| FortiWeb MCP transport | Default when FortiWeb is installed and desired | Preferred MCP route; falls back to Direct MCP with a warning |
| Direct MCP transport | Default fallback | Used when the FortiWeb route is unavailable or explicitly disabled |
| HTTPS gateway | Default, configurable | Self-signed HTTPS NodePorts; the operator can skip the playbook or provide certificate overrides |
| FortiAIGate syslog preservation | Configurable | Deployed when its AWS prep bucket exists; local and export behavior are documented separately |
| Open WebUI | Optional, disabled | Secondary UI; the custom chatbot owns the scenario experience |
| FAIG re-entry chain | Available, configurable, scenario-disabled | Global topology is enabled; every built-in scenario opts out by default |
| Functional scenario validation | Validated | `python3 -m functional_test` reads installed scenario metadata and verifies expected Alert, Deny, and Redact behavior |
| Dashboard load generation | Developer-only | Optional `load_test` workload; not part of setup or functional acceptance |
| FortiGate LLM and appliance-fronted FAIG traffic | Deferred | Configuration experiments remain available, but these are disabled and not baseline paths |

## Validated Scenario Baseline

| Scenario | Security story | Actions | MCP |
|---|---|---|---|
| `fortistore-injection` | Direct and compromised-frontend prompt injection | Alert, Deny | No |
| `hr-tool-dlp` | Sensitive data returned by a deterministic HR tool | Alert, Deny, Redact | Yes |
| `resume-tool-injection` | Indirect injection from a simulated uploaded resume and excessive tool access | Alert, Deny | Yes |

Canonical FAIG routes use `/v1/<scenario>/<action>/*`; guard names use
`<scenario>_<action>`. The testing-only bypass is `/v1/passthrough/*` with the
LiteLLM `pass-model` alias.

For Resume Tool Injection, Direct and Alert permit the synthetic cloud-tool
pivot. Deny stops the request after the poisoned document is read and before
the cloud tool executes. The Advanced least-privilege tool profile omits the
cloud tool and prevents the pivot by capability restriction. No real upload or
cloud access occurs. See the
[scenario walkthrough](../../chatbot/scenarios/examples/resume-tool-injection/README.md).

## Candidate And Archived Scenarios

`fortigate-operator` is the current candidate. It is retained for future work,
inactive, and not installed by the baseline scenario set.

Archived and superseded packages remain inspectable under
`archived_scenarios/` and in the catalog. They are historical material, not
supported scenarios. The machine-readable
[scenario catalog](../../chatbot/scenarios/examples/catalog.json) is the
authority for lifecycle and active state.

## Runtime Components And Ports

| Component | Namespace | Default external access |
|---|---|---|
| FortiAIGate | `fortiaigate` | `https://<k3s-ip>/ui/` for 8.0.1 |
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
| Local quickstart | Ollama through LiteLLM | Existing Ubuntu GPU host, local/LAN registry, ignored generated inventory, and optional existing appliances | Supported trusted-lab path |
| Manual quickstart | Same as selected lane | Operator runs Terraform and Ansible steps individually | Troubleshooting and recovery path |

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
  ignored local copies; updating a template requires an explicit reinstall or
  overwrite workflow so local instruction tuning is not silently replaced.
- FortiWeb MCP Security policy automation is unavailable through the current
  collection, so the supported FortiWeb role is transport/reverse proxy.
- Local NodePorts are for trusted labs and must not be exposed to untrusted
  networks.
- Private-k3s-subnet and appliance-fronted-only deployments require additional
  validation.
