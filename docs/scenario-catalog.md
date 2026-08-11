# Scenario Catalog Matrix

Status: transitional / pre-Phase-11.

This catalog is a compact map of the current scenario working set. Phase 10
keeps enough structure to continue testing, but Phase 11 is planned as the v1.0
baseline and will replace the current `demo-a`/`demo-b` model with generated
scenario metadata.

For operator commands and chatbot settings, use [scenarios.md](scenarios.md).
For the repeatable process used to create, tune, document, and correlate each
scenario, use
[scenario-documentation-process.md](scenario-documentation-process.md).

## Current Scenario Matrix

Phase 10 active scenarios:

| Scenario | MCP tool profile | Main story | Phase 11 decision needed |
|---|---|---|---|
| `fortistore-injection` | none; MCP off | Product-advisor prompt-injection and frontend/system-prompt injection demo | Decide whether it remains in the v1.0 baseline |
| `hr-tool-dlp` | `hr-tool-dlp` | MCP tool-result output-DLP demo | Decide whether it remains in the v1.0 baseline |

Phase 11 candidate scenarios:

| Candidate | Scenario profile | MCP tool profile | Main story | Phase 11 decision needed |
|---|---|---|---|---|
| FortiGate Operator | `fortigate-operator` | `fortigate-operator` | Read-only FortiGate status/configuration assistant | Decide whether FortiGate LLM proxy paths are generated as optional chatbot output paths |
| Resume clean control | `resume-screening-clean` | `resume-screening-clean` | Normal HR resume screening control path | Decide whether this remains separate or becomes a control entry point |
| Resume prompt injection | `resume-prompt-injection` | `resume-prompt-injection` | Indirect prompt injection from retrieved resume text | Define exact detect/protect path matrix |
| Resume tool pivot | `resume-cloud-tool-pivot` | `resume-cloud-tool-pivot` | Retrieved resume attempts to steer the agent into a different tool domain | Decide safe/vulnerable comparison structure |
| Resume tool pivot safe | `resume-cloud-tool-pivot-safe` | `resume-cloud-tool-pivot-safe` | Safe comparison for tool-pivot behavior | Decide whether it is an entry point or separate scenario |
| Resume tool pivot vulnerable | `resume-cloud-tool-pivot-vulnerable` | `resume-cloud-tool-pivot-vulnerable` | Vulnerable comparison for tool-pivot behavior | Decide whether it is an entry point or separate scenario |

## Current Compatibility Paths

The current demo still uses the compatibility route model:

| Path | Route | FortiAIGate role | Backend profile |
|---|---|---|---|
| Direct | LiteLLM direct | No FortiAIGate inspection | selected `demo-*` slot |
| FAIG Scan | `/v1/demo-a/*` | Detect/log only | selected backend slot |
| FAIG Protect | `/v1/demo-b/*` | Active input protection | selected backend slot |
| FAIG Output DLP | `/v1/demo-c/*` when enabled | Output DLP tuning | selected backend slot |
| FAIG Input DLP | `/v1/demo-d/*` when enabled | Input DLP tuning | selected backend slot |

These names are intentionally transitional. Do not expand new documentation
around them beyond what is needed for Phase 10 validation.

## Archived Scenario Material

Archived scenarios now live under `../archived_scenarios/` and are inactive in
`../chatbot/scenarios/examples/catalog.json`.

Archived material includes:

- Original MCP-backed FortiStore product-advisor experiment.
- Fast-food/menu-poisoning experiments.
- HR policy and support-ticket profiles.

They can be inspected with:

```bash
python3 scripts/scenario_profiles.py list --include-inactive
python3 scripts/scenario_profiles.py show fastfood-ordering --include-inactive
```

## Phase 11 Handoff

Phase 11 should own the final scenario matrix:

- scenario-owned FAIG paths,
- generated LiteLLM aliases,
- generated chatbot simplified and advanced dropdowns,
- generated MCP profile selection,
- optional FortiGate chatbot output paths when enabled,
- optional Direct versus FortiWeb MCP path combinations when enabled,
- generated FAIG GUI work order.
