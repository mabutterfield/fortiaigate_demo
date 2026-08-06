# Scenario Profiles

Status: Phase 11 v1.0 baseline in progress.

Scenario profiles package repeatable demo instructions, MCP tool expectations,
and prompt examples. They do not deploy separate MCP servers; every scenario
uses the same shared MCP service and declares its expected tools in
`required_tools`.

Tracked Phase 10 active scenarios and Phase 11 candidate scenarios live under
`examples/`. Archived or legacy scenarios live under the repo-level
`archived_scenarios/` directory. The catalog remains at `examples/catalog.json`
and can point at either location.

Phase 11 installs editable local scenario packages and generates scenario-owned
paths, aliases, chatbot profiles, frontend instructions, and MCP selections.
The old `demo-a`, `demo-b`, and `frontend` slots remain compatibility-only and
are not expanded by the Phase 11 runtime.

## Current Scenario Sets

The current working set is intentionally small.

Phase 10 active scenarios:

| Scenario | Location | Purpose |
|---|---|---|
| FortiStore Injection | `examples/fortistore-injection/` | Product-advisor prompt-injection and frontend/system-prompt injection demo |
| HR Tool DLP | `examples/hr-tool-dlp/` | MCP tool-result output-DLP demo |

Phase 11 candidate scenarios:

| Scenario family | Location | Purpose |
|---|---|---|
| FortiGate Operator | `examples/fortigate-operator/` | Read-only FortiGate operations assistant candidate |
| HR Resume | `examples/resume-*/` | Resume screening, indirect prompt injection, and tool-pivot candidates |

All other scenario folders have been moved to `archived_scenarios/` and marked
inactive in `examples/catalog.json`.

The catalog lifecycle distinguishes `baseline`, `candidate`, and `archived`.
Normal list, install, and validation commands select only the two baseline
scenarios. Candidate packages remain tracked and discoverable but are not part
of the v1.0 baseline validation set.

The two Phase 11 baseline profiles use `schema_version: 2` and the generation
contract in `scenario-profile-v2.schema.json`. Candidate profiles remain in
their current pre-migration format until they are selected for future work.

## Phase 11 Local Scenario Lifecycle

Install editable, ignored local copies from the repo root:

```bash
python3 scripts/scenario_profiles.py add fortistore-injection
python3 scripts/scenario_profiles.py add hr-tool-dlp
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

Removal archives the editable package under the ignored `_removed/` tree and
records its FAIG paths as stale. FAIG GUI objects are never deleted
automatically. After manually removing stale objects, acknowledge them with:

```bash
python3 scripts/scenario_profiles.py ack-stale fortistore-injection
```

The matrix builder deterministically expands installed scenarios into the
LiteLLM aliases, backend instruction profiles, chatbot simplified and advanced
controls, MCP paths and tool profiles, scenario-owned FAIG routes, and the FAIG
GUI work order. LiteLLM and the chatbot consume their matrix slices when
`demo_configuration_source: scenario_matrix` (the default). FAIG GUI objects
remain a generated manual work order. Use `--debug-all-server-tools` only when
intentionally exposing every tool reported by the MCP server for
troubleshooting.

In advanced chatbot mode, `All Installed Scenario Tools` is the expanded
cross-domain MCP set; the scenario-named profile is the scoped default. Direct
MCP is always available for an MCP-enabled installed scenario. FortiWeb MCP is
added only when the proxy is desired and an installed appliance endpoint is
available. The simplified profiles keep the scenario's normal MCP choice so
the advanced alternate does not multiply every preset.

## Catalog And Compatibility Commands

Use the helper from the repo root:

```bash
python3 scripts/scenario_profiles.py list
python3 scripts/scenario_profiles.py list --include-candidates
python3 scripts/scenario_profiles.py list --include-inactive
python3 scripts/scenario_profiles.py show hr-tool-dlp
python3 scripts/scenario_profiles.py install hr-tool-dlp --slot demo-a --force
python3 scripts/scenario_profiles.py validate
```

`install --slot` is the temporary Phase 10 compatibility workflow. New Phase
11 work should use `add` and the ignored local scenario packages above.

Inactive archived scenarios can still be inspected for reference:

```bash
python3 scripts/scenario_profiles.py show fastfood-ordering --include-inactive
```

Instruction profiles remain the place to fine-tune local wording after a
scenario has been installed.

## Related Docs

- Operator-facing scenario guidance: `docs/scenarios.md`
- Scenario editing and deploy boundaries: `docs/scenario-authoring.md`
- Scenario creation/evidence process: `docs/scenario-documentation-process.md`
- Archived scenario notes: `archived_scenarios/README.md`
