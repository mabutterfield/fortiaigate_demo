# Advanced Scenario Management

This page contains optional operator workflows intentionally omitted from the
normal [Scenario Management](scenario-management.md) path. Use it to inspect
non-baseline packages, tune an installed scenario, diagnose generated matrix
content, or make deliberate Detailed-mode comparisons.

All commands run from `<repo_root>`. Set `FAIG_INVENTORY` and
`FAIG_HOST_ALIAS` as described in Scenario Management before running live
deployment or validation commands.

## Candidate And Archived Packages

The normal list contains only validated baseline scenarios. Include candidates
when evaluating future material:

```bash
python3 scripts/scenario_profiles.py list --include-candidates
python3 scripts/scenario_profiles.py show fortigate-operator --include-candidates
```

Include archived material only for troubleshooting or historical comparison:

```bash
python3 scripts/scenario_profiles.py list --include-inactive
python3 scripts/scenario_profiles.py show <scenario-id> --include-inactive
```

Candidate and archived scenarios are not part of installation readiness and
must not be presented as validated baseline demonstrations.

## Tuning

An installed package is an ignored, operator-owned copy:

```text
chatbot/scenarios/local/<scenario-id>/
├── profile.json
├── instructions.txt
└── optional frontend instructions and supporting files
```

Edit this copy rather than the tracked example. Common changes include:

- backend `instructions.txt` wording;
- frontend instruction profiles;
- prompts and validation metadata;
- scenario and extended MCP tool sets;
- FortiWeb versus Direct MCP intent;
- tool-round and context limits; and
- the disabled-by-default FAIG re-entry setting.

Keep the scenario ID stable unless the intent is to author a distinct scenario.
After tuning, validate and preview the matrix, redeploy the affected consumers,
re-render the work order, update FortiAIGate objects when generated fields
changed, and run functional validation.

## Matrix Validation And Diagnostics

Validate tracked baseline packages and installed local packages:

```bash
python3 scripts/scenario_profiles.py validate
python3 scripts/scenario_profiles.py render-work-order
```

Successful package validation prints one `ok (baseline)` line per validated
scenario and exits zero. Any schema, missing-file, unresolved-tool, duplicate,
or naming error is printed with the affected scenario and exits nonzero.
`render-work-order` also validates the installed set before it prints the
terminal work order and writes its Markdown version.

Inspect the complete generated consumer contract only when diagnosing a
specific field:

```bash
python3 scripts/scenario_profiles.py show-matrix
```

`show-matrix` prints JSON for LiteLLM aliases and instructions, chatbot
profiles, MCP transports and tools, FortiAIGate work-order entries, chains,
capabilities, and warnings. It is diagnostic output, not a sequence of manual
steps. This offline preview is not given the deployed FortiWeb inventory, so
its MCP fallback warnings do not establish whether a live FortiWeb listener is
available. Use Demo Outputs and the deployed chatbot validation for that
decision.

## Detailed Chatbot Comparisons

Simplified mode is the normal presenter workflow. Detailed mode permits
intentional changes without editing scenario metadata, including:

- Direct MCP instead of FortiWeb MCP;
- a least-privilege scenario tool profile instead of its extended profile;
- `all-installed` for a deliberate cross-domain demonstration;
- a different frontend instruction profile; or
- FAIG passthrough for a protection-free comparison.

Reset the conversation after changing these controls so earlier messages and
tool results do not alter the comparison.

MCP scenarios share one server. Scenario profiles expose the least-privilege
tool set by default; extended and `all-installed` profiles intentionally widen
access. MCP transport is independent of the FortiAIGate LLM route.

## Optional FAIG Re-entry

FAIG re-entry is globally available but disabled by every built-in scenario.
Enable `matrix.faig_chain.enabled` only in an installed local profile when
deliberately demonstrating instruction visibility or alternate routing. After
changing the profile, redeploy LiteLLM and the chatbot, then render a new work
order. Existing Alert, Deny, and Redact objects remain unchanged.

The enabled matrix adds this dedicated object:

| Field | Generated value |
|---|---|
| Scenario | `<scenario-id>` |
| Action | `chain` |
| Flow Name | `<scenario-id>-faig-chain` |
| Scenario Path | `/v1/<scenario-id>/faig-chain/*` |
| Guard Name | `<scenario-id>_faig_chain` |
| Guard Template | `alert_all` |
| Guard Protections | `inject_alert`, `output_dlp_alert` |
| Next-hop Model | `<scenario-id>-faig-chain` |

Create the dedicated AI Guard and Flow from that work-order row. The Flow
points to the Guard, and the Guard points to the generated
`<scenario-id>-faig-chain` LiteLLM model. LiteLLM injects the scenario
instructions and re-enters FortiAIGate only through `/v1/passthrough/*`, where
`pass_model` terminates the chain at `pass-model` with `no_protections`.

Never point the passthrough Guard or downstream model back to a
`*-faig-chain` alias; that creates a request loop. Run the Python functional
validator after configuring the additional Flow and Guard.

## Updates, Backups, And Removal

Preview an available tracked update without modifying local content:

```bash
python3 scripts/scenario_profiles.py update <scenario-id>
```

An intentional forced update first backs up the installed package under the
ignored `chatbot/scenarios/local/_backups/` tree:

```bash
python3 scripts/scenario_profiles.py update <scenario-id> --force
```

Removal archives the package under ignored `_removed/` state. Neither update
nor removal changes FortiAIGate GUI objects automatically; reconcile those
objects with the newly rendered work order.
