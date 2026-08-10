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
export FAIG_HOST_ALIAS={{ubuntu-hostname}}
# or
export FAIG_INVENTORY=cloud
export FAIG_HOST_ALIAS=faig-aws
```

For local mode, use the Ubuntu hostname recorded as the host alias by
`local_setup.py`.

`FAIG_INVENTORY` is a shell convenience used throughout the documentation.
Set it once in each new shell so the same commands operate on either the
repository-root `cloud` or `local` inventory link.

## 1. Discover And Inspect

List the validated built-ins or inspect one profile without installing it:

```bash
python3 scripts/scenario_profiles.py list
python3 scripts/scenario_profiles.py show hr-tool-dlp
```

Candidate and archived package inspection is intentionally omitted from the
normal installation path. See
[Advanced Scenario Management](advanced-scenario-management.md#candidate-and-archived-packages)
when evaluating non-baseline material.

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

## 3. Optionally Tune A Local Scenario

Normal installation uses the scenario exactly as shipped. To change backend
or frontend instructions, prompts, tool sets, transport intent, round limits,
or FAIG re-entry, edit only the ignored installed copy and follow
[Advanced Scenario Management: Tuning](advanced-scenario-management.md#tuning).

## 4. Render The Work Order

Render the manual GUI work order:

```bash
python3 scripts/scenario_profiles.py render-work-order
```

The command validates installed packages first. On success it prints a
terminal-friendly list of the required scenario objects and ends with:

```text
Markdown version: docs/raw-output/scenario-work-orders/faig-scenario-work-order.md
```

Open that ignored Markdown file for the formatted table. An invalid installed
package instead produces a specific error and exits nonzero; use
[Advanced Scenario Management: Matrix Validation And Diagnostics](advanced-scenario-management.md#matrix-validation-and-diagnostics)
to diagnose it.

Re-render after every install, local edit, forced update, or removal. The work
order owns each scenario path, Flow Name, Guard Name, Guard Template, Guard
Protections, and next-hop model alias.

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
| Detailed UI selection only | None |
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

Create every required guard and flow. FortiAIGate activates each object when
it is created; there is no separate scenario-object deployment step. The
normal built-in next hop is the LiteLLM model alias matching the scenario ID.

## 7. Validate The Configured Paths

Immediately after the FortiAIGate objects are created, validate passthrough
and every declared case for the installed scenarios:

```bash
python3 -m functional_test validate \
  --inventory "$FAIG_INVENTORY" \
  --host-alias "$FAIG_HOST_ALIAS"
```

The validator selects the declared chatbot profiles itself; you do not need
to select one manually in the browser first. Restrict a troubleshooting run
without changing its expected-result rules:

```bash
python3 -m functional_test validate \
  --inventory "$FAIG_INVENTORY" \
  --host-alias "$FAIG_HOST_ALIAS" \
  --scenario-id hr-tool-dlp
```

The live test is authoritative for frontend instructions, MCP execution,
FortiWeb transport, tool order, denial before a forbidden tool, and redaction.

## 8. Select A Chatbot Profile

Use Simplified mode for the validated comparison. One profile selects the
model, LLM path, frontend instructions, MCP state and transport, scoped tools,
context, and tool-round limit together.

Use Detailed mode to deliberately change one component—for example Direct MCP
instead of FortiWeb, a least-privilege base tool profile instead of an extended
profile, or `all-installed` for a cross-domain demonstration. Reset the
conversation when comparing profiles so previous messages do not change the
result.

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
[Scenario Authoring](scenario-authoring.md). For tuning, candidate inspection,
matrix diagnostics, and expanded tool/transport controls, see
[Advanced Scenario Management](advanced-scenario-management.md). For
deployment failures, see [Troubleshooting](troubleshooting.md).
