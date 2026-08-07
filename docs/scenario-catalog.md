# Scenario Catalog Matrix

Status: v1.0 scenario baseline.

The tracked catalog classifies templates. The ignored installed-scenario state
controls the runtime matrix. See [Scenario Runbook](scenarios.md) for lifecycle
commands and [Scenario Documentation Process](scenario-documentation-process.md)
for evidence requirements.

## Validated Baseline Scenarios

| Scenario | Security story | Actions | LiteLLM alias | MCP default |
|---|---|---|---|---|
| `fortistore-injection` | Direct and compromised-frontend prompt injection | Alert, Deny | `fortistore-injection` | Disabled |
| `hr-tool-dlp` | Sensitive data returned by a simulated HR tool | Alert, Deny, Redact | `hr-tool-dlp` | `hr-tool-dlp` |
| `resume-tool-injection` | Indirect injection from a simulated uploaded resume and excessive tool access | Alert, Deny | `resume-tool-injection` | `resume-tool-injection-cloud-pivot` |

These are the active, validated baseline templates. Installing one
creates an editable copy under `chatbot/scenarios/local/<scenario-id>/`.

Resume Tool Injection was last validated on the local Jarvis environment on
2026-08-06. Its enforcement result is determined from the MCP tool trace, not
only from response wording.

## Future Candidates

The following templates survived legacy cleanup but are not active or
validated scenarios. Leave them untouched until future work explicitly
migrates and tests them.

| Candidate | Current profile | Intended story |
|---|---|---|
| FortiGate Operator | `fortigate-operator` | Read-only FortiGate operations assistant |

Candidate templates remain discoverable with:

```bash
python3 scripts/scenario_profiles.py list --include-candidates
```

## Generated Runtime Surface

For each installed baseline scenario, the matrix generates:

- one LiteLLM alias matching the scenario ID;
- one backend instruction mapping loaded from the operator-owned local package;
- scenario-owned FAIG route names and URIs;
- simplified chatbot profiles;
- advanced model, FAIG route, frontend instruction, MCP path, and MCP tool
  profile controls;
- one scenario-scoped MCP tool profile when MCP is enabled;
- the optional `all-installed` MCP profile for cross-domain demonstrations;
- a manual FAIG GUI work order.

Global controls are always `pass-model` and `/v1/passthrough`. Simplified mode
shows passthrough only when no scenarios are installed; advanced mode always
retains it.

FortiWeb MCP appears only when its proxy is desired and an installed endpoint
is present. FortiGate LLM routes remain disabled. The FAIG re-entry capability
is globally available, while every built-in scenario opts out by default.

## Archived Material

Archived scenarios live under `../archived_scenarios/` and are inactive in
`../chatbot/scenarios/examples/catalog.json`. They are reference material, not
runtime choices:

```bash
python3 scripts/scenario_profiles.py list --include-inactive
python3 scripts/scenario_profiles.py show fastfood-ordering --include-inactive
```

Legacy slot names remain in explicit compatibility commands only. Do not use
them when authoring new scenarios or documenting the current runtime.
