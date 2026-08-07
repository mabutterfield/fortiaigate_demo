# Deployment Options

Review this page before the first automated quickstart. “Default” describes
repository intent; a missing license, inventory, endpoint, or other prerequisite
can still cause a safe skip or fallback. All commands run from `<repo_root>`.

Operator overrides belong in ignored `ansible/group_vars/user.yml`, shared
`terraform/user.tfvars`, or the relevant module's ignored
`99-local.auto.tfvars`. Do not edit tracked `00-system.auto.tfvars` or
`ansible/group_vars/system.yml` for a local installation choice.

## Option Matrix

| Feature | Default | AWS behavior | Local behavior | Why configurable | Prerequisites | Enable/disable control | Validation command | Operational/security impact |
|---|---|---|---|---|---|---|---|---|
| FortiGate | Desired; optional to core | Terraform deploys a two-interface appliance and Ansible applies its baseline when prerequisites exist | Configures an existing appliance only when local inventory exists | License/cost, deployment time, topology, or demo focus | AWS Marketplace terms and BYOL file/token for AWS; reachable appliance and managed credential for local | `--no-fortigate` or `--no-appliances`; module `fortigate_enabled=false`; `--include-fortigate` makes absence an error | `ansible-playbook -i cloud-fortigate ansible/playbooks/status_fortigate.yml` or `-i local-fortigate` | Adds cost and management exposure; current scenario baseline does not require FortiGate LLM routing |
| FortiWeb | Desired; optional to core | Terraform deploys FortiWeb; Ansible builds the MCP reverse proxy when prerequisites exist | Configures an existing two-sided appliance when local inventory exists | License/cost, proxy topology, configuration time, or isolation | AWS Marketplace terms and BYOL file/token for AWS; reachable appliance interfaces for local | `--no-fortiweb` or `--no-appliances`; module `fortiweb_enabled=false`; `--include-fortiweb` makes absence an error | `ansible-playbook -i cloud-fortiweb ansible/playbooks/status_fortiweb.yml` or `-i local-fortiweb` | Adds cost and an MCP network hop; missing FortiWeb must not break core deployment |
| FortiWeb versus Direct MCP | FortiWeb preferred when installed and desired; Direct fallback | Chatbot uses the generated FortiWeb listener when available | Same behavior using local port1/backend addressing | Troubleshooting isolation, missing appliance, latency, or demonstrating transport controls | Running MCP plus a usable FortiWeb proxy endpoint for FortiWeb mode | `--no-fortiweb` or `fortiweb_mcp_proxy_enabled: false` forces Direct fallback; scenario metadata selects its desired path | `python3 -m functional_test --mcp-path fortiweb` or `--mcp-path direct` | FortiWeb changes transport only; it does not expand the scenario's tool set |
| FAIG re-entry chain | Globally available; disabled in every built-in scenario | Optional scenario request can return through `/v1/passthrough/*` after LiteLLM instruction injection | Same | Show LiteLLM-added instructions to FAIG and preserve future routing flexibility | Canonical FAIG passthrough flow and loop-safe `pass-model` downstream alias | Global `faig_chain_capability_enabled`; local installed profile `matrix.faig_chain.enabled` for per-scenario opt-in | `python3 scripts/scenario_profiles.py show-matrix` | Incorrect downstream routing can loop; never point re-entry back to a chain alias |
| MCP server and tool exposure | MCP server and browser MCP enabled | Shared in-cluster synthetic tool server | Same | Demo focus, least privilege, model/tool reliability, or isolation | Deployed MCP server and scenario-declared tools | `mcp_enabled`, `chatbot_mcp_enabled`; simplified mode uses scenario tools; Advanced may select `all-installed`; debug all-server tools is explicit | `ansible-playbook -i cloud ansible/playbooks/status_mcp.yml` or `-i local`; then `python3 -m functional_test` | `all-installed` deliberately broadens cross-domain access; scoped scenario profiles are the normal least-privilege choice |
| Open WebUI | Disabled and unconfigured | Deployable as an additional chart | Deployable as an additional chart | Future/custom UI experiments and resource use | None beyond the k3s app layer; operator supplies any meaningful custom configuration | `openwebui_enabled: true` in ignored user vars | `ansible-playbook -i <cloud-or-local> ansible/playbooks/status_openwebui.yml` | No supported scenario/provider configuration or validation is supplied; not part of the demo acceptance path |
| HTTPS gateway and certificates | Gateway enabled; quickstart asks before deployment; self-signed | Exposes generated HTTPS NodePorts | Same on the trusted LAN | Browser/API encryption, certificate trust, port exposure, or simpler HTTP troubleshooting | Generated HTTPS ports; optional private certificate/key outside Git | Decline the quickstart prompt or set `demo_https_gateway_enabled: false`; override `demo_https_gateway_cert_local_path` and key path for private material | `ansible-playbook -i <cloud-or-local> ansible/playbooks/validate_demo_http_paths.yml` | Self-signed certificates require explicit trust; private keys and certificates remain outside Git |
| Syslog collector and preservation | Collector is in the normal app sequence; S3 preservation disabled by tracked AWS defaults | Writes S3 only when the prep bucket is enabled; otherwise file output | File output unless a custom remote path is supplied | Stop-gap preservation when FortiAnalyzer is unavailable, plus retention and S3 cost | Running k3s; optional prep S3 bucket/IAM for durable AWS storage | `fortiaigate_syslog_bucket_enabled` and lifecycle vars control S3; omitting the collector requires a customized/manual app sequence | `ansible-playbook -i <cloud-or-local> ansible/playbooks/status_fortiaigate_syslog_collector.yml` | Not a FortiAnalyzer replacement; local/file output can be lost with the pod or lab unless exported |
| Public versus private k3s | Public | Prep-owned EIP and trusted-CIDR NodePort access | Existing trusted-LAN address | External exposure versus private routing requirements | Public: EIP and trusted CIDRs. Private: operator network path and downstream routing | `k3s_subnet_mode = "public"` or `"private"` in `terraform/aws-ec2-k3s/99-local.auto.tfvars` | `terraform -chdir=terraform/aws-ec2-k3s output k3s_subnet_mode` | Private mode and appliance-fronted-only access need additional validation; do not select private without a working management/data path |
| Bedrock versus Ollama | Bedrock for AWS; Ollama for local | LiteLLM proxies scenario aliases to allowed Bedrock models | LiteLLM proxies to in-cluster Ollama | Cloud cost/quota, offline/local operation, GPU capacity, model quality, or data locality | AWS credentials/model access or local NVIDIA GPU plus model storage | Deployment lane selects the default; advanced `scenario_matrix_llm_target_overrides` can map alternate targets | AWS: `ansible-playbook -i cloud ansible/playbooks/test_model_direct.yml`; local: `FAIG_DEPLOYMENT_TARGET=local ansible-playbook -i local ansible/playbooks/test_model_direct.yml` | Local Ollama NodePort has no built-in authentication; model choice materially affects tool-call reliability |
| Functional validation and load generation | Functional validation supported; load generation opt-in | Runs against deployed AWS environment | Runs against local lab | Acceptance versus developer dashboard traffic, time, tokens, GPU use, and energy | Installed scenarios and reachable chatbot; load test additionally needs an intentional workload window | `python3 -m functional_test`; developer options under `python3 -m load_test` | `python3 -m functional_test` | Load generation is not setup validation and may create sustained resource use; stop it gracefully |
| Container source and publication | ECR for AWS; local/LAN registry for local | Terraform owns ECR and generated pull values; publisher loads vendor archives and builds chatbot | Publisher targets configured local registry | Existing registry, account separation, offline lab, publishing time, and storage cost | Docker plus AWS login/ECR or reachable local registry | `registry_backend`, `registry_type`, local registry variables, quickstart publish choice | See [Container Repository Management](container-repository-management.md#verification) | Image content changes require a new tag for releases; mutable development tags can conceal stale content |

`<cloud-or-local>` means the root `cloud` or `local` inventory alias. Appliance
commands use the matching `cloud-fortigate`, `cloud-fortiweb`,
`local-fortigate`, or `local-fortiweb` alias.

## Default-On Appliances Are Conditional

FortiGate and FortiWeb are desired by default, not hard dependencies of the
core k3s deployment. Without an explicit `--include-*` requirement, quickstart
reports a missing license/inventory prerequisite and continues without that
appliance. Explicit `--no-*` flags record operator intent and suppress the
associated Terraform/Ansible path.

FortiWeb is also the preferred MCP transport. If the scenario asks for
FortiWeb but the generated matrix cannot prove that a desired appliance and
usable endpoint exist, it emits a warning and selects Direct MCP.

## Tool Exposure Choices

MCP path and MCP tool exposure are separate controls:

- the path selects Direct MCP or FortiWeb transport;
- the scenario tool profile exposes only tools required by that scenario;
- `All Installed Scenario Tools` is an intentional Advanced-mode expansion for
  cross-domain demonstrations; and
- the full server tool list is a troubleshooting option, not a normal profile.

Synthetic tools and data are designed for realistic demonstrations but do not
access real HR, uploaded-file, cloud, or customer systems.

## Choosing The Smallest Useful Deployment

Common reasons to alter defaults include:

- disable both appliances for the fastest core FAIG/LiteLLM/chatbot build;
- disable FortiWeb to isolate MCP behavior from the network proxy;
- keep scenario-scoped tools for a least-privilege story;
- disable HTTPS temporarily to isolate certificate or gateway failures;
- disable Open WebUI because it has no baseline configuration;
- omit S3 syslog preservation when FortiAnalyzer is present or retention cost
  is unwanted; and
- use local Ollama where cloud access or token cost is undesirable, after
  validating that the selected model reliably supports the scenario tools.
