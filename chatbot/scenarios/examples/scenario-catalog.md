# Scenario Catalog

This page is the human-readable view of the adjacent machine-readable
[`catalog.json`](catalog.json). The catalog classifies tracked templates; it
does not report what is installed. Use
`python3 scripts/scenario_profiles.py list-installed` for installed state and
[Scenario Management](../../../docs/scenario-management.md) for the lifecycle.

## Validated Built-Ins

| Scenario | Security story | Actions | LiteLLM alias | MCP profile |
|---|---|---|---|---|
| [`fortistore-injection`](fortistore-injection/README.md) | User and compromised-frontend prompt injection against a product advisor | Alert, Deny | `fortistore-injection` | Disabled |
| [`hr-tool-dlp`](hr-tool-dlp/README.md) | Synthetic sensitive HR records returned by a tool | Alert, Redact, Deny | `hr-tool-dlp` | Base `hr-tool-dlp` |
| [`resume-tool-injection`](resume-tool-injection/README.md) | Indirect injection from a simulated uploaded resume and excessive tool access | Alert, Deny | `resume-tool-injection` | Base `resume-tool-injection`; extended `resume-tool-injection-cloud-pivot` |

Installing one creates an editable, Git-ignored copy under
`chatbot/scenarios/local/<scenario-id>/`. Built-in FAIG re-entry is disabled.
FortiWeb is the normal MCP transport when it is available; Direct MCP is the
fallback.

## Candidate

| Scenario | Intended story | Validation status |
|---|---|---|
| `fortigate-operator` | Read-only FortiGate operations assistant | Future candidate; not a validated demo |

Show candidates with:

```bash
python3 scripts/scenario_profiles.py list --include-candidates
```

Candidate content is intentionally left unchanged until it is selected for
migration and validation.

## Archived Reference Material

The inactive catalog entries point into `archived_scenarios/`. They include
retired standalone resume experiments that were consolidated into
`resume-tool-injection` and older legacy demonstrations. They are references,
not installable validated choices.

```bash
python3 scripts/scenario_profiles.py list --include-inactive
```

Do not infer installation or support status from a directory that happens to
exist. The `lifecycle` and `active` fields in `catalog.json` classify tracked
content; ignored local state controls the installed runtime matrix.
