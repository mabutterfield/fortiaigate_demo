# Scenario Authoring Guide

Phase 11 scenario templates live under
`chatbot/scenarios/examples/<scenario-id>/`. Templates are read-only inputs to
the installer. Operator-owned, editable copies live under the ignored
`chatbot/scenarios/local/<scenario-id>/` tree.

Only `fortistore-injection` and `hr-tool-dlp` are validated baseline scenarios.
Do not migrate or modify the six candidate packages until a future phase
selects them.

## Package Contents

A schema-v2 scenario package contains:

- `profile.json`: identity, prompts, MCP requirements, path roles, frontend
  instruction profiles, and simplified chatbot profiles;
- `instructions.txt`: backend instructions loaded by LiteLLM;
- optional frontend instruction files;
- optional `curl-payloads/`, scenario screenshots, and a scenario README.

The schema is `chatbot/scenarios/scenario-profile-v2.schema.json`. Scenario IDs
are lowercase kebab-case and become the LiteLLM alias.

## Local Edit Workflow

Install the tracked template once:

```bash
python3 scripts/scenario_profiles.py add <scenario-id>
python3 scripts/scenario_profiles.py list-installed
```

Edit files under `chatbot/scenarios/local/<scenario-id>/`. Git pulls do not
overwrite those files. Deploy after local scenario changes:

```bash
ansible-playbook ansible/playbooks/deploy_litellm.yml
ansible-playbook ansible/playbooks/deploy_chatbots.yml
```

Check whether the tracked source or local package changed:

```bash
python3 scripts/scenario_profiles.py update <scenario-id>
```

Replace the local package only when explicitly requested:

```bash
python3 scripts/scenario_profiles.py update <scenario-id> --force
```

Forced update first moves the previous package to the ignored `_backups/`
tree. This is the expected update/overwrite warning boundary.

## Matrix Contract

`profile.json` `matrix` owns these runtime objects:

| Field | Purpose |
|---|---|
| `llm_target` | Environment-neutral backend target, normally `llm-default` |
| `instruction_profile` | Backend instruction source, position, and enabled state |
| `entry_points` | Semantic FAIG roles and guard templates |
| `frontend_instruction_profiles` | Named chatbot-local instruction choices |
| `chatbot_profiles` | Simplified presets combining LLM, FAIG, MCP, context, and frontend settings |
| `faig_chain` | Optional advanced FAIG re-entry chain; disabled in the baseline |

Generated route names are `<scenario-id>-<path-role>`. Generated flow URIs are
`/v1/<scenario-id>/<path-role>`. Suggested guard names use underscores. Every
scenario route points to the scenario ID as its next-hop LiteLLM model.

`detect` is the canonical detection role. Other baseline roles are
`protect-input`, `input-dlp`, `output-dlp-deny`, and `output-dlp-redact`.

Inspect generated output before deployment:

```bash
python3 scripts/scenario_profiles.py show-matrix
python3 scripts/scenario_profiles.py render-work-order
python3 scripts/build_scenario_matrix.py --output /tmp/scenario-matrix.json
```

## MCP Tool Profiles

The MCP server exposes one shared tool catalog. The chatbot filters schemas
before sending them to the model:

- a scenario-named profile exposes only the scenario's `required_tools`;
- `all-installed` is the optional expanded cross-domain demonstration set;
- `all-server` appears only when the explicit debug flag is enabled;
- an MCP-disabled scenario does not run the agent tool loop.

Direct MCP is the scenario default. FortiWeb may be selected as an advanced
alternate when its proxy is both desired and installed. Do not create duplicate
simplified profiles for every MCP transport.

Use `--mcp-path fortiweb` in the headless harness when testing that alternate:

```bash
python3 scripts/scenario_test_harness.py \
  --scenario hr-tool-dlp \
  --path-role direct \
  --mcp-path fortiweb
```

## Frontend Instruction Profiles

Frontend instructions are named files in the scenario package. Simplified
profiles select the intended name; advanced mode can select `none`, the
scenario profile, or another installed profile.

Frontend instructions are not LiteLLM backend instructions. Keep deliberately
unsafe fixtures clearly labeled, and never place secrets in them. A local
frontend edit requires chatbot redeployment but does not require an image
rebuild.

## Simplified Profiles

Each simplified profile should describe one demo intent, not one transport
combination. It selects:

- provider path (`direct` or `faig-static`);
- scenario model alias and optional route;
- context mode/window;
- frontend instruction profile;
- MCP enabled state, normal MCP path, tool profile, and tool-round limit.

Use presenter-facing labels such as `Detect Only`, `Protect Input`, or
`Output DLP Redact`. The advanced UI remains available for alternate tool sets
and MCP transports.

## Validation

Validate structure and deterministic generation:

```bash
python3 scripts/scenario_profiles.py validate
python3 scripts/build_scenario_matrix.py >/tmp/scenario-matrix.json
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/smoke_test.py
```

Run a scenario role through the deployed chatbot agent:

```bash
python3 scripts/scenario_test_harness.py \
  --scenario <scenario-id> \
  --path-role <path-role>
```

Raw curl payloads under `curl-payloads/` simulate tool-result-like content for
FAIG/LiteLLM testing. Use the chatbot UI or harness when real MCP tool
selection and execution are part of the test.

## Deploy Boundaries

| Change | Required action |
|---|---|
| Add/remove/edit installed scenario backend instructions | Deploy LiteLLM; deploy chatbot for generated profile/route changes |
| Edit installed frontend instructions or matrix chatbot profiles | Deploy chatbot |
| Change chatbot or `agent_probe.py` code | Bump image tag, publish image, deploy chatbot |
| Change MCP tool code, schemas, fixture data, or credential wiring | Deploy MCP |
| Select another advanced model, route, frontend profile, MCP path, or tool profile | No redeploy |
| Change FAIG entry points | Re-render work order and manually update FAIG GUI objects |

## Removal

```bash
python3 scripts/scenario_profiles.py remove <scenario-id>
python3 scripts/scenario_profiles.py render-work-order
```

Removal archives the local package and records stale FAIG objects. It never
deletes appliance configuration. After manual cleanup:

```bash
python3 scripts/scenario_profiles.py ack-stale <scenario-id>
```

Phase 10 slot commands remain compatibility-only and should not appear in new
scenario designs or runbooks.
