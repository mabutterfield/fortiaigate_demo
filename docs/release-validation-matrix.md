# Release Validation

This maintainer guide defines the checks required before tagging the repository
v1.0 baseline. It is not part of the normal operator quickstart. Record the
environment, date, commit, result, evidence location, and reason for every
intentional skip outside Git or in the release system.

All commands run from `<repo_root>`.

## 1. Repository Health

```bash
git status --short
python3 scripts/scenario_profiles.py validate
python3 scripts/instruction_profiles.py validate
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/smoke_test.py
```

Required result: clean intended tree, valid scenario/instruction metadata,
passing unit tests, Terraform formatting, inventory-link checks, Python
compilation, tracked-file safety checks, and every Ansible syntax check.

## 2. Documentation Contract

Verify:

- current Markdown links and anchors resolve;
- commands assume `<repo_root>` and use documented inventory links;
- current docs contain no obsolete internal-planning or lettered-slot runtime language;
- generated scenario paths, flows, guards, aliases, transports, tool profiles,
  frontend profiles, and Simplified labels match metadata;
- every functional curl mapping matches its validation case and model alias;
- screenshot placeholders match the external capture inventory; and
- primary navigation advertises functional validation but not developer load
  generation.

## 3. Fresh Deployment

Complete at least one intentional fresh deployment for each release-supported
lane:

| Lane | Required evidence |
|---|---|
| AWS | Preparation and options reviewed; quickstart completes; selected default/optional appliances report their actual installed or skipped state; consolidated URLs print |
| Local | Local setup generates inventory; quickstart completes against Ubuntu 24.04 GPU host; consolidated URLs print |

Confirm Terraform/Ansible reruns converge to the same desired state and that an
interrupted component can be recovered through Operations.

## 4. Initial FortiAIGate Configuration

From current documentation only:

1. complete first login and licensing;
2. create the shared LiteLLM provider;
3. configure `pass-model`;
4. create/deploy the minimal passthrough guard and `/v1/passthrough/*` flow;
5. prove passthrough returns without scenario instructions or protections; and
6. capture required screenshots without secrets.

## 5. Scenario Installation And GUI Objects

Install the three validated scenarios, deploy matrix consumers, render the
work order, and create every required FAIG object:

```bash
python3 scripts/scenario_profiles.py add fortistore-injection
python3 scripts/scenario_profiles.py add hr-tool-dlp
python3 scripts/scenario_profiles.py add resume-tool-injection
python3 scripts/scenario_profiles.py render-work-order
```

Required protected paths:

| Scenario | Actions |
|---|---|
| `fortistore-injection` | Alert, Deny |
| `hr-tool-dlp` | Alert, Redact, Deny |
| `resume-tool-injection` | Alert, Deny |

Confirm FortiWeb is selected for MCP when installed and usable, Direct MCP is
the fallback, and FAIG re-entry remains disabled in every built-in profile.

## 6. Functional Scenario Validation

Run the same setup validator advertised to operators:

```bash
python3 -m functional_test validate \
  --inventory "$FAIG_INVENTORY" \
  --host-alias "$FAIG_HOST_ALIAS"
```

Required result: `INSTALLATION READY` with every path at expected results over
total results. Review tool traces so Resume Deny omits
`cloud_bucket_list_demo`, HR Redact replaces all protected values, and every
required tool appears.

Render and inspect at least one direct-flow request from each scenario:

```bash
python3 -m functional_test render-curl \
  --scenario fortistore-injection --action deny --case deny-attack
python3 -m functional_test render-curl \
  --scenario hr-tool-dlp --action redact --case redact-attack
python3 -m functional_test render-curl \
  --scenario resume-tool-injection --action deny --case deny-attack
```

Compare the rendered path, model, prompt, frontend instructions, and tool
boundary with installed metadata. Curl is not a substitute for the live MCP
agent-loop result.

## 7. Optional Components

Validate only selected components, while confirming an absent optional
component does not break the core deployment:

- FortiGate status and configuration when installed;
- FortiWeb MCP proxy plus Direct fallback;
- HTTPS gateway and certificate behavior;
- syslog collector and preservation intent;
- Open WebUI deployment only when deliberately enabled, with no claim of a
  preconfigured scenario integration; and
- Bedrock or Ollama model target appropriate to the deployment lane.

Experimental FortiGate proxy/application-control paths are historical
investigations, not release-blocking scenario paths.

## 8. Update, Backup, Removal, And Teardown

Verify on a disposable scenario installation:

- ordinary update inspection does not overwrite local tuning;
- `update --force` creates a recoverable ignored backup;
- removal archives local state and updates the generated matrix;
- remote FAIG objects remain a documented manual reconciliation boundary; and
- automated teardown removes deployment resources without deleting retained
  repositories contrary to the documented repository contract.

## 9. Optional Dashboard Workload

Load generation is not required to prove scenario correctness. When dashboard
traffic is a release demonstration objective, run a bounded calibration only
after functional validation passes. Follow
[Developer Load Testing](development/load-testing.md) and record duration,
request bounds, concurrency, shutdown result, statistics, and GPU collection
status.

## Final Gate

Do not tag until:

- automated checks pass;
- required fresh-deployment lanes have recorded results;
- passthrough and all seven protected action paths are operational;
- the functional validator reports every expected result;
- documentation and screenshots have completed human review; and
- no secrets, inventories, local scenario state, generated evidence, or
  internal plans are tracked.
