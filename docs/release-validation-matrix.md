# Release Validation Matrix

Status date: 2026-07-29

This matrix is the Phase 10 release-maintainer checklist for deciding whether
the next tag is `v1.0.0` or a `v0.10.0` release candidate. It is not a normal
operator quickstart step.

Record every skipped item with a reason. Do not tag `v1.0.0` until the no-apply
checks and at least one AWS fresh deployment validation pass have succeeded.

## Result Summary

| Category | Current status | Evidence |
|---|---|---|
| No-apply repository health | Passed | `smoke_test.py`, scenario profile validation, instruction profile validation, and scenario harness help passed on 2026-07-29. |
| AWS fresh deployment | Pending | Requires an intentional fresh AWS run. |
| AWS teardown | Pending | Requires a matching teardown after AWS validation. |
| Local fresh deployment | Pending | Requires an intentional local run against the Ubuntu lab host. |
| Scenario baseline | Pending | Requires live chatbot/MCP/route validation. |
| Traffic generator | Partial live pass | `path_test` and a one-request local `faig-scan` traffic run passed; long steady/burst tuning remains pending. |
| FortiGate application-control traffic investigation | Planned | Optional Phase 10 investigation; not a v1.0 release blocker unless selected for the recorded demo. |

## No-Apply Repository Health

Run these from the repo root:

```bash
python3 scripts/smoke_test.py
python3 scripts/scenario_profiles.py validate
python3 scripts/instruction_profiles.py validate
python3 scripts/scenario_test_harness.py --help
python3 scripts/traffic_generator.py --help
python3 scripts/traffic_generator.py --dry-run
python3 scripts/traffic_generator.py --mode traffic --dry-run --scenario-source family --use-case steady --duration 60 --rate 6
python3 scripts/traffic_generator.py --mode traffic --dry-run --scenario fortistore-injection --use-case burst
```

Expected coverage:

| Check | Expected result |
|---|---|
| Python compile | All tracked Python scripts compile. |
| Script help | Supported scripts print help and exit cleanly. |
| Secret/local-file guard | No generated local vars, secrets, kubeconfigs, licenses, or Terraform state are tracked. |
| Terraform formatting | `terraform fmt -check` passes for tracked Terraform files. |
| Ansible syntax | Tracked playbooks pass syntax checks without applying changes. |
| Scenario metadata | Scenario and instruction profile validation passes. |
| Traffic generator dry-runs | Default path test prints inferred targets without sending traffic; steady and burst traffic plans print request mix without sending traffic. |

Result log:

| Date | Result | Notes |
|---|---|---|
| 2026-07-29 | Passed | `python3 scripts/smoke_test.py`, `python3 scripts/scenario_profiles.py validate`, `python3 scripts/instruction_profiles.py validate`, `python3 scripts/scenario_test_harness.py --help`, `python3 scripts/traffic_generator.py --help`, default path-test dry-run, and traffic-generator steady/burst dry-runs passed. |

## AWS Fresh Deployment

Use the default supported path:

```bash
python3 scripts/automated_quickstart.py
```

For rebuilds where Terraform is already applied:

```bash
python3 scripts/automated_quickstart.py --skip-terraform
```

Required validation points:

| Area | Command or evidence | Expected result |
|---|---|---|
| AWS identity/profile | quickstart caller-identity check | Valid profile before Terraform. |
| ECR create/import | quickstart ECR state report | Existing repositories imported or new repositories created intentionally. |
| Chatbot image tag | `chatbot_image_tag` in repo/user vars | Branch-version releases intentionally bump or confirm the chatbot tag before publishing. |
| AWS prep | Terraform apply output | IAM, EIPs, S3 syslog resources when enabled, and generated vars created. |
| EC2 k3s foundation | EC2 READY check and `validate_k3s.yml` | Instance, system status, Kubernetes, DNS, NVIDIA runtime are healthy. |
| FortiGate | `status_fortigate.yml`, `configure_fortigate.yml` | Appliance reachable; managed objects compare/apply cleanly when enabled. |
| FortiWeb | `status_fortiweb.yml`, `configure_fortiweb.yml` | Appliance reachable; reverse-proxy baseline validates when enabled. |
| Image publishing | selected publish playbooks | Required image repositories are available from ECR. |
| FortiAIGate | `status_fortiaigate.yml`, `validate_faig.yml` after readiness | FortiAIGate reports READY and deeper checks pass after GUI boundary is handled. |
| LiteLLM | `status_litellm.yml`, `validate_litellm.yml`, `test_litellm_direct.yml` | Bedrock-backed aliases respond. |
| MCP | `status_mcp.yml`, `validate_mcp.yml`, `test_mcp.yml` | Shared MCP server responds and tool catalog is current. |
| Syslog collector | `status_fortiaigate_syslog_collector.yml`, `test_fortiaigate_syslog_collector.yml` | UDP test message reaches collector when the bucket exists. |
| Chatbot | `status_chatbots.yml`, `validate_chatbots.yml` | Custom chatbot is reachable. |
| Demo home | `status_demo_home.yml`, `validate_demo_home.yml` | Demo home prints expected direct and appliance URLs. |
| HTTPS gateway | `deploy_demo_https_gateway.yml`, generated HTTPS URLs | Self-signed HTTPS paths respond when deployed. |
| Open WebUI | `status_openwebui.yml`, `validate_openwebui.yml` | Required only when `openwebui_enabled=true`. |
| Demo outputs | `show_demo_outputs.yml` | FortiAIGate GUI setup values and validation commands are printed. |

Result log:

| Date | Result | Notes |
|---|---|---|
| 2026-07-29 | Pending | Full AWS validation not run in this doc-only slice. |

## AWS Teardown

Use:

```bash
python3 scripts/automated_teardown.py
```

Required validation points:

| Area | Expected result |
|---|---|
| FortiAIGate syslog export | S3 syslog objects export before bucket cleanup when present. |
| FortiWeb destroy | FortiWeb state is destroyed before shared network dependencies. |
| FortiGate destroy | FortiGate state is destroyed before shared network dependencies. |
| EC2 k3s destroy | k3s foundation state is destroyed after app validation is complete. |
| AWS prep destroy | Syslog bucket is emptied safely; no `BucketNotEmpty` failure. |
| ECR preservation | ECR repositories are removed from Terraform state before destroy so image repositories are retained. |

Result log:

| Date | Result | Notes |
|---|---|---|
| 2026-07-29 | Pending | Must follow an intentional AWS validation run. |

## Local Fresh Deployment

Use:

```bash
python3 scripts/local_setup.py
python3 scripts/automated_quickstart.py --local
```

Manual local checks should pass `FAIG_DEPLOYMENT_TARGET=local` and the local
inventory:

```bash
FAIG_DEPLOYMENT_TARGET=local ansible-playbook \
  -i ansible/inventory/local.generated.ini \
  ansible/playbooks/status_demo_home.yml
```

Required validation points:

| Area | Expected result |
|---|---|
| Local generated var lifecycle | `local_setup.py` creates ignored inventory/vars; `local_var_cleanup.py export/import` preserves and restores local generated files without committing them. |
| SSH/default reuse | Rerun uses saved local host and SSH values without re-entering data. |
| GPU discovery | GPU UUIDs and product names are captured when `nvidia-smi` is available. |
| GPU assignment | FortiAIGate and Ollama use the selected UUIDs or documented defaults. |
| Local registry | k3s can pull required images from the generated local/LAN registry. |
| k3s bootstrap | Bootstrap and validation are idempotent against the existing Ubuntu host. |
| FortiAIGate | Deploy/status works against local k3s. |
| Ollama | `deploy_ollama.yml`, `status_ollama.yml`, and `validate_ollama.yml` pass. |
| LiteLLM to Ollama | LiteLLM local alias validates through the in-cluster Ollama service. |
| Chatbot/demo home | Local URLs render and point at local NodePorts. |
| Local FortiGate | Managed `apiadmin` onboarding and status/config playbooks work when the appliance is present. |
| Local FortiWeb | Managed `apiadmin` onboarding and status/config playbooks work when the appliance is present. |
| FortiWeb MCP path | Direct MCP and FortiWeb MCP paths are both validated when configured. |

Result log:

| Date | Result | Notes |
|---|---|---|
| 2026-07-29 | Pending | Do not interrupt a live local run; record results after the current operator-owned pass completes. |

## Scenario Baseline

Baseline scenarios:

| Scenario | Required tool profile | Required first path |
|---|---|---|
| `fortistore-injection` | none; MCP off | Direct LiteLLM |
| `hr-tool-dlp` | `hr-tool-dlp` | Direct MCP |

Inactive legacy and in-progress scenario profiles remain in
`chatbot/scenarios/examples/` but are hidden from default validation until
reactivated in `chatbot/scenarios/examples/catalog.json`.

Headless example:

```bash
python3 scripts/scenario_test_harness.py \
  --scenario fortistore-injection \
  --paths direct \
  --mcp-path direct \
  --run-label phase10-baseline
```

Run each scenario through direct first. Repeat through `faig-scan`,
`faig-protect`, and FortiWeb MCP only after the matching FortiAIGate GUI routes,
guards, and FortiWeb proxy path are configured.

Result log:

| Date | Scenario | Result | Notes |
|---|---|---|---|
| 2026-07-29 | baseline set | Pending | Live scenario validation is intentionally separate from this doc commit. |

## Traffic Generator

Use [Traffic Generator](traffic-generator.md) for command details.

Steady use case:

```bash
python3 scripts/traffic_generator.py \
  --mode traffic \
  --target local \
  --use-case steady \
  --duration 3600 \
  --rate 6 \
  --route faig-scan \
  --label local-dashboard-hour \
  --yes
```

Burst use case:

```bash
python3 scripts/traffic_generator.py \
  --mode traffic \
  --target local \
  --use-case burst \
  --scenario fortistore-injection \
  --route direct \
  --label local-burst-test \
  --yes
```

Expected validation points:

| Area | Expected result |
|---|---|
| Path test | No-argument default prints the inferred FAIG HTTPS endpoint and verifies `/v1/demo-a`, `/v1/demo-b`, and `/v1/passthrough` once. |
| Steady mode | Persistent but not excessive requests populate FortiAIGate charts and logs over time. |
| Burst mode | Short high-rate traffic exercises load behavior and any DoS-style protections selected for the lab. |
| Active-slot sync | Default live runs read `demo-a`/`demo-b` metadata and send scenarios matching the loaded instruction slot. |
| Security dispositions | Blocked and redacted responses are counted as `security_disposition`, not as transport failures. |
| Safeguards | AWS/public long or high-rate runs refuse without `--allow-cloud-long-run`. |
| Output | `plan.json`, `events.jsonl`, and `summary.json` are written under ignored `docs/raw-output/traffic/<run-label>/`. |

Result log:

| Date | Use case | Result | Notes |
|---|---|---|---|
| 2026-07-29 | steady dry-run | Passed | Request mix printed without sending traffic. |
| 2026-07-29 | burst dry-run | Passed | Request mix printed without sending traffic; cloud burst guard also refused execution without explicit opt-in. |
| 2026-07-29 | path test | Passed | No-argument local run reached `https://192.168.248.80` from the workstation and returned HTTP 200 for `/v1/demo-a`, `/v1/demo-b`, and `/v1/passthrough`. |
| 2026-07-29 | scan smoke | Passed with warning | One clean `faig-scan` traffic request completed through the deployed chatbot pod. The running chatbot image did not support `--tool-profile`, so per-scenario MCP tool selection requires a chatbot image rebuild/redeploy. |

## FortiGate Application-Control Traffic Investigation

Phase 10E investigates whether traffic from a VM behind FortiGate can produce
synthetic traffic that is classified by FortiGate Application Control and
therefore creates useful FortiGate app-control logs for the demo. It also
defines separate inbound paths through FortiGate to LiteLLM and FortiAIGate for
deep inspection comparison.

This should generate lab traffic that causes FortiGate to log recognizable
application-control events. It should not directly insert, forge, or present
fabricated FortiGate log records as real appliance telemetry.

Candidate validation points:

| Area | Expected result |
|---|---|
| Traffic path | Traffic traverses a FortiGate policy with logging and an application-control profile enabled. |
| Routed VM | Outbound AI app tests run direct/no-proxy from a VM or lab host behind FortiGate. |
| Explicit proxy | Optional workstation proxy tests use a script-scoped explicit proxy URL rather than changing workstation routing or global proxy environment. |
| AI inspection | `http://<fgt-ip>:4000/v1` forwards to LiteLLM with `certificate-inspection`; `https://<fgt-ip>/v1/...` forwards to FortiAIGate with `custom-deep-inspection`. Both policies use Application Control `default` and full traffic logging. |
| Synthetic identity | Requests include a clear lab label where possible, such as hostnames, paths, or user agents that identify the run. |
| App-control evidence | FortiGate logs show application name/category/action fields for the generated flow. |
| Correlation | Traffic-generator run label and timestamps can be correlated with FortiGate logs and FortiAIGate logs. |
| Safeguards | Cloud/long-running traffic still requires explicit opt-in from the traffic generator. |

Runbook: [FortiGate Traffic Demo](fortigate-proxy-demo.md)

This is optional for v1.0 unless the recorded demo selects the FortiGate
application-control log story.
