# Scenario Management

Scenarios are installable demo packages that generate LiteLLM aliases,
backend instructions, chatbot profiles, MCP tool selections, FortiAIGate
routes, and a manual FortiAIGate GUI work order. The tracked packages under
`chatbot/scenarios/examples/` are read-only sources. Each installation is an
editable, Git-ignored copy under `chatbot/scenarios/local/<scenario-id>/`.

The [Scenario Catalog](../chatbot/scenarios/examples/scenario-catalog.md)
classifies tracked packages. Catalog status does not mean a scenario is
installed. `list-installed` is the authority for the current installation.

All commands run from `<repo_root>`.

## Select The Deployment

The repository-root `local` and `cloud` links point at the generated Ansible
inventories. Choose the one you are operating on and its host alias:

```bash
export FAIG_INVENTORY=local
export FAIG_HOST_ALIAS=jarvis
# or
export FAIG_INVENTORY=cloud
export FAIG_HOST_ALIAS=faig-aws
```

Replace `jarvis` when local setup created a different host alias.

## 1. Discover And Inspect

List the validated built-ins, include future candidates, or inspect one
profile without installing it:

```bash
python3 scripts/scenario_profiles.py list
python3 scripts/scenario_profiles.py list --include-candidates
python3 scripts/scenario_profiles.py show hr-tool-dlp
```

Use candidate material for evaluation only. Do not present it as validated.
Archived packages are reference material and appear only with
`--include-inactive`.

## 2. Install An Editable Copy

Install one or more validated scenarios:

```bash
python3 scripts/scenario_profiles.py add fortistore-injection
python3 scripts/scenario_profiles.py add hr-tool-dlp
python3 scripts/scenario_profiles.py add resume-tool-injection
python3 scripts/scenario_profiles.py list-installed
```

`add` copies the tracked template into ignored local state. It will not
overwrite an existing local package. Pulling repository changes also leaves
installed packages untouched.

## 3. Tune Local Instructions Or Metadata

Edit only the installed copy:

```text
chatbot/scenarios/local/<scenario-id>/
├── profile.json
├── instructions.txt
└── optional frontend instructions and supporting files
```

Typical local changes include instruction wording, prompts, simplified
profiles, MCP transport intent, scenario/extended tool sets, and tool-round
limits. Keep the scenario ID stable unless creating a separate scenario.

MCP scenarios use one shared MCP server. Their base profile exposes only
scenario tools. An extended profile adds an intentional comparison set, and
`all-installed` exposes the union of installed scenario tools for explicit
cross-domain demonstrations. Normal Simplified profiles select one scoped
base or extended set; choosing `all-installed` is an Advanced-mode decision.

FortiWeb is the normal MCP transport when it is installed, configured, and
desired. Matrix generation warns and uses Direct MCP when FortiWeb is not
available. The MCP transport is independent of the FortiAIGate LLM route.

FAIG re-entry is globally available. Every built-in scenario sets
`matrix.faig_chain.enabled` to `false`; enable it only in an operator-owned
local profile after reviewing
[FortiAIGate Scenario GUI Configuration](fortiaigate-gui-config.md#6-keep-faig-re-entry-disabled-unless-deliberately-testing-it).

## 4. Preview The Matrix And Work Order

Validate packages, preview all generated consumers, and render the manual GUI
work order:

```bash
python3 scripts/scenario_profiles.py validate
python3 scripts/scenario_profiles.py show-matrix
python3 scripts/scenario_profiles.py render-work-order
```

Re-run these commands after every install, local edit, forced update, or
removal. The work order owns each scenario path, flow, guard, guard template,
and next-hop model alias.

## 5. Deploy Matrix Consumers

Deploy LiteLLM and the chatbot after installing or changing a scenario:

```bash
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_litellm.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_chatbots.yml
```

Deploy MCP only when MCP server code, schemas, fixtures, or credentials
changed. Installing a scenario normally selects tools that already exist on
the shared MCP server.

| Change | Required deployment |
|---|---|
| Backend instructions or model mapping | LiteLLM |
| Installed profile, generated routes, frontend instructions, or Simplified profiles | Chatbot; LiteLLM when backend mapping/instructions also changed |
| MCP code, schema, fixture, or credential wiring | MCP |
| Advanced UI selection only | None |
| Scenario entry point or action | Render a new work order and update FortiAIGate manually |

Ansible brings a deployed component back to the declared state, so these
playbooks are safe to rerun after an interrupted or partial deployment.

## 6. Configure FortiAIGate

Complete [FortiAIGate Initial Configuration](FortiAIGate-initial-config.MD)
once, then follow [Scenario GUI Configuration](fortiaigate-gui-config.md) for
each row in the generated work order. Built-in paths follow:

```text
/v1/<scenario-id>/<action>/*
```

Create and deploy every required guard and flow. A draft GUI object is not an
active route. The normal built-in next hop is the LiteLLM model alias matching
the scenario ID.

## 7. Select A Chatbot Profile

Use Simplified mode for the validated comparison. One profile selects the
model, LLM path, frontend instructions, MCP state and transport, scoped tools,
context, and tool-round limit together.

Use Advanced mode to deliberately change one component—for example Direct MCP
instead of FortiWeb, a least-privilege base tool profile instead of an extended
profile, or `all-installed` for a cross-domain demonstration. Reset the
conversation when comparing profiles so previous messages do not change the
result.

## 8. Validate The Installation

Validate passthrough and every declared test case for all installed scenarios:

```bash
python3 -m functional_test validate \
  --inventory "$FAIG_INVENTORY" \
  --host-alias "$FAIG_HOST_ALIAS"
```

Restrict the metadata-driven run without changing its expected-result rules:

```bash
python3 -m functional_test validate \
  --inventory "$FAIG_INVENTORY" \
  --host-alias "$FAIG_HOST_ALIAS" \
  --scenario-id hr-tool-dlp
```

The live functional test is authoritative for chatbot frontend instructions,
MCP execution, FortiWeb transport, tool order, denial before a forbidden tool,
and redaction. A transcript replay sends a preconstructed tool exchange
directly to a FAIG flow and proves only raw guard/model handling; it does not
prove the chatbot or MCP server executed that exchange.

## 9. Update Without Losing Local Work

Check whether an installed package differs from its source without modifying
it:

```bash
python3 scripts/scenario_profiles.py update <scenario-id>
```

Replace it only when you intend to discard its current installed contents:

```bash
python3 scripts/scenario_profiles.py update <scenario-id> --force
```

The forced operation first copies the installed package into the ignored
`chatbot/scenarios/local/_backups/` tree. Review or restore local tuning from
that backup, redeploy the affected consumers, update manual FortiAIGate
objects when the work order changed, and rerun functional validation.

## 10. Remove An Installed Scenario

```bash
python3 scripts/scenario_profiles.py remove <scenario-id>
python3 scripts/scenario_profiles.py render-work-order
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_litellm.yml
ansible-playbook -i "$FAIG_INVENTORY" ansible/playbooks/deploy_chatbots.yml
```

Removal moves the local package into the ignored `_removed/` tree. It does not
delete FortiAIGate GUI objects; disable or remove those flows and guards
manually after confirming nothing references them.

## Validated Scenario Runbooks

- [FortiStore Injection](../chatbot/scenarios/examples/fortistore-injection/README.md)
- [HR Tool DLP](../chatbot/scenarios/examples/hr-tool-dlp/README.md)
- [Resume Tool Injection](../chatbot/scenarios/examples/resume-tool-injection/README.md)

For package schema and authoring decisions, see
[Scenario Authoring](scenario-authoring.md). For deployment failures, see
[Troubleshooting](troubleshooting.md).
