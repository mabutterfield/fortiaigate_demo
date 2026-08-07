# Scenario Packages

Scenario profiles package repeatable demo instructions, MCP tool expectations,
and prompt examples. They do not deploy separate MCP servers; every scenario
uses the same shared MCP service and declares its expected tools in
`required_tools`.

Tracked baseline and candidate templates live under `examples/`.
Archived or legacy scenarios live under the repo-level
`archived_scenarios/` directory. The catalog remains at `examples/catalog.json`
and can point at either location.

The current runtime installs editable local scenario packages and generates
scenario-owned paths, aliases, chatbot profiles, frontend instructions, and
MCP selections.

## Current Scenario Set

The [Scenario Catalog](examples/scenario-catalog.md) is the human-readable
authority for validated, candidate, and archived scenario status. The
machine-readable `examples/catalog.json` owns the same lifecycle state for
tools. Do not duplicate the scenario matrix in package documentation.

Baseline profiles use `schema_version: 2` and the generation
contract in `scenario-profile-v2.schema.json`. Candidate profiles remain in
their current pre-migration format until they are selected for future work.

## Package And Runtime Boundaries

Each package owns metadata, backend instructions, optional frontend
instructions, prompts, expected traces, and documentation. It does not own a
separate MCP service or an independent appliance deployment.

MCP-enabled packages select a base scenario tool profile and may define an
extended comparison profile. `all-installed` is generated from the union of
installed scenario tools for an intentional Advanced-mode cross-domain demo;
it is not the normal Simplified selection. FortiWeb is preferred when its MCP
proxy is installed and usable, with Direct MCP as the fallback.

The optional FAIG re-entry chain is globally available. Built-in packages keep
it disabled with `matrix.faig_chain.enabled: false`; changing that value is an
operator-owned local customization.

## Local Scenario Lifecycle

Install editable, ignored local copies from the repo root:

```bash
python3 scripts/scenario_profiles.py add fortistore-injection
python3 scripts/scenario_profiles.py add hr-tool-dlp
python3 scripts/scenario_profiles.py add resume-tool-injection
python3 scripts/scenario_profiles.py list-installed
python3 scripts/scenario_profiles.py show-matrix
python3 scripts/scenario_profiles.py render-work-order
python3 scripts/build_scenario_matrix.py --output /tmp/scenario-matrix.json
```

Installed packages live under `chatbot/scenarios/local/<scenario-id>/`. Edit
the local `instructions.txt`, profile, or frontend instruction files without
changing the tracked example. Normal commands and `git pull` never overwrite
these local files.

Check for tracked-template or local changes without overwriting anything:

```bash
python3 scripts/scenario_profiles.py update fortistore-injection
```

Explicitly replace a local package from the tracked example:

```bash
python3 scripts/scenario_profiles.py update fortistore-injection --force
```

Forced update first moves the existing package into the ignored
`chatbot/scenarios/local/_backups/` tree. Pulling updated examples does not
update an installed scenario until this explicit command is run.

Remove a scenario from installed state:

```bash
python3 scripts/scenario_profiles.py remove fortistore-injection
python3 scripts/scenario_profiles.py render-work-order
```

Removal archives the editable package under the ignored `_removed/` tree. The
environment is disposable, so local scenario state does not track remote FAIG
objects after removal; rebuild or adjust the GUI separately when needed.

The matrix builder deterministically expands installed scenarios into the
LiteLLM aliases, backend instruction profiles, chatbot simplified and advanced
controls, MCP paths and tool profiles, scenario-owned FAIG routes, and the FAIG
GUI work order. LiteLLM and the chatbot consume their matrix slices when
`demo_configuration_source: scenario_matrix` (the default). FAIG GUI objects
remain a generated manual work order. Use `--debug-all-server-tools` only when
intentionally exposing every tool reported by the MCP server for
troubleshooting.

In Advanced chatbot mode, `All Installed Scenario Tools` is the expanded
cross-domain MCP set; the scenario-named profile is the scoped default. Direct
MCP is always available for an MCP-enabled installed scenario. FortiWeb MCP is
added only when the proxy is desired and an installed appliance endpoint is
available. The simplified profiles keep the scenario's normal MCP choice so
the advanced alternate does not multiply every preset.

## Catalog Commands

Use the helper from the repo root:

```bash
python3 scripts/scenario_profiles.py list
python3 scripts/scenario_profiles.py list --include-candidates
python3 scripts/scenario_profiles.py list --include-inactive
python3 scripts/scenario_profiles.py show hr-tool-dlp
python3 scripts/scenario_profiles.py validate
```

Inactive archived scenarios can still be inspected for reference:

```bash
python3 scripts/scenario_profiles.py show fastfood-ordering --include-inactive
```

Instruction profiles remain the place to fine-tune local wording after a
scenario has been installed.

## Related Documentation

- [Operator lifecycle](../../docs/scenario-management.md)
- [Scenario editing and deploy boundaries](../../docs/scenario-authoring.md)
- [Scenario creation and evidence process](../../docs/scenario-documentation-process.md)
- [Archived scenario notes](../../archived_scenarios/README.md)
