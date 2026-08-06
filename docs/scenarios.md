# Scenario Demo Runbook

Status: Phase 11 v1.0 baseline.

Runtime configuration is generated from ignored installed scenario packages.
Tracked examples are read-only templates. The baseline contains only
`fortistore-injection` and `hr-tool-dlp`; the six surviving candidates remain
untouched for future work.

## Install The Baseline

```bash
python3 scripts/scenario_profiles.py list
python3 scripts/scenario_profiles.py add fortistore-injection
python3 scripts/scenario_profiles.py add hr-tool-dlp
python3 scripts/scenario_profiles.py list-installed
python3 scripts/scenario_profiles.py render-work-order
```

Deploy matrix consumers:

```bash
ansible-playbook ansible/playbooks/deploy_litellm.yml
ansible-playbook ansible/playbooks/deploy_chatbots.yml
```

Local packages live under `chatbot/scenarios/local/<scenario-id>/`. Tune their
instructions or profiles without changing tracked templates or creating Git
pull conflicts.

## Generated Baseline Matrix

| Scenario | Model alias | MCP | Required FAIG roles | Optional role |
|---|---|---|---|---|
| `fortistore-injection` | `fortistore-injection` | off | `detect`, `protect-input` | none |
| `hr-tool-dlp` | `hr-tool-dlp` | Direct MCP, tool profile `hr-tool-dlp` | `detect`, `output-dlp-deny`, `output-dlp-redact` | `input-dlp` |

Global controls are `pass-model` and `/v1/passthrough`. See the
[Scenario Catalog](scenario-catalog.md) for candidate/archive status and the
[FAIG GUI walkthrough](FortiAIGate-initial-config.MD) for flow creation.

## Chatbot Use

The chatbot defaults to Simplified mode. One generated Demo Profile selects
the model, provider/route, context, frontend instruction profile, MCP enabled
state, MCP path, scoped tools, and tool-round limit.

Switch to Advanced mode to select components separately:

- Direct LiteLLM or a generated FAIG static route;
- `pass-model` or an installed scenario alias;
- `none` or a named installed frontend profile;
- Direct MCP or FortiWeb MCP when that installed alternate is desired;
- scenario tools or `all-installed` for an intentional cross-domain demo.

FortiGate LLM paths and intelligent FAIG header routes are not part of the
baseline.

## Scenario Walkthroughs

- [FortiStore Injection](../chatbot/scenarios/examples/fortistore-injection/README.md)
- [HR Tool DLP](../chatbot/scenarios/examples/hr-tool-dlp/README.md)

## Headless Tests

The harness uses semantic path roles and resolves all other settings from the
installed matrix:

```bash
python3 scripts/scenario_test_harness.py \
  --scenario fortistore-injection \
  --path-role direct \
  --path-role detect \
  --path-role protect-input

python3 scripts/scenario_test_harness.py \
  --scenario hr-tool-dlp \
  --path-role direct \
  --path-role detect \
  --path-role output-dlp-deny \
  --path-role output-dlp-redact
```

Test the advanced MCP alternate without changing simplified profiles:

```bash
python3 scripts/scenario_test_harness.py \
  --scenario hr-tool-dlp \
  --path-role direct \
  --mcp-path fortiweb
```

Raw FAIG connectivity tests also come from the matrix:

```bash
python3 scripts/traffic_generator.py --mode path_test
python3 scripts/traffic_generator.py \
  --mode path_test \
  --path-test-path hr-tool-dlp-output-dlp-redact
```

## Update And Overwrite Behavior

Check without modifying local files:

```bash
python3 scripts/scenario_profiles.py update <scenario-id>
```

Explicitly replace from the tracked template:

```bash
python3 scripts/scenario_profiles.py update <scenario-id> --force
```

The force operation creates an ignored backup first. Pulling repo updates does
not update installed scenarios; the operator must choose the force operation,
then redeploy LiteLLM/chatbot and update manual FAIG objects.

## Removal

```bash
python3 scripts/scenario_profiles.py remove <scenario-id>
python3 scripts/scenario_profiles.py render-work-order
```

Removal archives local files and records stale FAIG flows/guards. It never
deletes appliance configuration. Remove those objects manually, then run:

```bash
python3 scripts/scenario_profiles.py ack-stale <scenario-id>
```

## Deploy Boundaries

| Change | Action |
|---|---|
| Local backend instructions | Deploy LiteLLM |
| Installed profile, routes, simplified profiles, frontend file | Deploy chatbot; deploy LiteLLM when backend mapping/instructions changed |
| Chatbot or agent-probe code | Bump/publish image, then deploy chatbot |
| MCP tools, schemas, fixtures, or credential wiring | Deploy MCP |
| Advanced UI selection only | No redeploy |
| FAIG entry point | Re-render work order and update the GUI manually |

## Candidate And Compatibility Material

Show future candidates without installing them:

```bash
python3 scripts/scenario_profiles.py list --include-candidates
```

Archived material remains under `archived_scenarios/` and is reference-only.
Explicit Phase 10 slot/path flags remain for old tests, but new runbooks and
scenario designs must use scenario IDs and path roles.
