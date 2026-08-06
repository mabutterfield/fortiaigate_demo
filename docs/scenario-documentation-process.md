# Scenario Documentation Process

Status: Phase 11 v1.0 baseline.

Use this process when creating, tuning, validating, or promoting a scenario.
Scenario documentation describes semantic actions; the install tooling generates
the exact model aliases, FAIG paths, chatbot profiles, and MCP selections.

## Source And Runtime Boundaries

| Content | Location | Ownership |
|---|---|---|
| Baseline or candidate template | `chatbot/scenarios/examples/<scenario-id>/` | Tracked, read-only source |
| Installed scenario | `chatbot/scenarios/local/<scenario-id>/` | Ignored, operator-editable runtime copy |
| Archived material | `archived_scenarios/` | Tracked reference only |
| Generated FAIG work order | `docs/raw-output/scenario-work-orders/` | Ignored, installation-specific |
| Test evidence | `docs/raw-output/scenarios/<scenario-id>/` | Ignored until deliberately reviewed |

Do not tune tracked examples for one installation. Add the scenario locally,
edit the ignored copy, and promote only generally useful changes back to the
template in a deliberate review.

## Scenario Record

Each scenario profile and README should identify:

- scenario ID, lifecycle (`baseline`, `candidate`, or `archived`), and demo goal;
- security feature under test;
- FAIG actions and whether each action is required for release;
- guard template, expected disposition, and next-hop scenario model alias per action;
- backend instructions and named frontend instruction profiles;
- MCP enabled state, required tool names, scoped tool profile, and maximum tool
  rounds;
- prompt sequence, including no-context and with-context variants where useful;
- expected direct, Alert, Deny, and Redact behavior;
- evidence locations, FAIG correlation fields, and known tuning gaps.

The profile is the machine-readable contract. The README explains how to
configure guards and demonstrate the story without duplicating generated
installation state.

## Canonical Actions

Use only actions needed by the scenario:

| Action | Purpose |
|---|---|
| `direct` | LiteLLM control path; not a FAIG flow |
| `alert` | Allow traffic and record relevant detections |
| `deny` | Prevent delivery when the scenario protection triggers |
| `redact` | Redact protected data and allow the remainder |
| `redact-dummy` | Reserved for future input-DLP replacement behavior |

The scenario identifies the protection story; the final path segment identifies
the FAIG action. Do not assign path meaning by letter or slot position.

## Authoring And Validation Workflow

1. Define the demo goal and security boundary.
2. Choose the smallest useful action set and narrowest MCP tool set.
3. Create or update the tracked candidate template and validate its schema.
4. Add an editable local copy:

   ```bash
   python3 scripts/scenario_profiles.py add <scenario-id>
   python3 scripts/scenario_profiles.py validate
   python3 scripts/scenario_profiles.py show-matrix
   python3 scripts/scenario_profiles.py render-work-order
   ```

5. Deploy LiteLLM and the chatbot so both consume the same installed matrix.
6. Create FAIG guards and flows from the generated work order. Copy the exact
   configured URI, including the trailing `/*`.
7. Validate direct and `alert` controls before enforcement actions.
8. Exercise each enforcement action and capture response plus FAIG event evidence.
9. Record observed behavior and open tuning gaps in the scenario README.
10. Promote a candidate to `baseline` only after its required actions are
    repeatable and the active catalog/runbooks have been reviewed.

Tracked candidates that are not selected for work remain untouched and are not
installed by the baseline workflow.

## Context And DLP Notes

Document where protected data first appears:

- user input;
- prior conversation context;
- MCP tool arguments or results;
- model output.

That location determines whether input DLP, output DLP, or both are relevant.
For a multi-turn test, record the retained context mode, number of prior
messages, maximum tool rounds, and whether the same result reproduces with a
single-turn control prompt.

For output DLP, test both a single protected value and a multi-record response.
A guard that handles one value can still miss repeated or differently formatted
values. Keep safe display fields out of the protected PII list when the demo
needs them visible to make the redaction result understandable.

## Screenshots

Use the reusable [FAIG GUI walkthrough](FortiAIGate-initial-config.MD) for the
common page sequence. Its `{{variable}}` tokens are replaced with values from
the generated work order.

Store a screenshot in the scenario folder only when it demonstrates settings
or evidence unique to that scenario. In the scenario README, state which token
values the screenshot uses and link back to the common walkthrough.

Do not include credentials, API keys, private endpoint details, or unrelated
customer data in screenshots.

## Test Commands

Run a semantic action through the chatbot-owned agent loop:

```bash
python3 scripts/scenario_test_harness.py \
  --scenario <scenario-id> \
  --action <action>
```

Test raw FAIG route connectivity from the generated matrix:

```bash
python3 scripts/traffic_generator.py --mode path_test
python3 scripts/traffic_generator.py \
  --mode path_test \
  --path-test-path <generated-flow-name>
```

For MCP scenarios, record the selected MCP path, tool profile, actual tool
calls, and tool-round count. Direct MCP is the normal baseline. FortiWeb MCP is
an optional advanced alternate when desired and installed.

## Evidence

Recommended ignored evidence names:

| Evidence | Pattern |
|---|---|
| Raw result | `docs/raw-output/scenarios/<scenario-id>/<yyyymmdd>-<action>.json` |
| FAIG/syslog extract | `docs/raw-output/scenarios/<scenario-id>/<yyyymmdd>-faig-<action>.jsonl` |
| Scenario-specific screenshot | `chatbot/scenarios/examples/<scenario-id>/images/<action>-<purpose>.png` |

For each run, correlate scenario ID, action, request path, timestamp, flow, guard,
model alias, detector/action, and final disposition. Record whether the result
was allowed, denied, redacted, or failed before reaching the guard.

Raw captures can contain local endpoints or synthetic protected data. Review
them before committing, and never commit credentials or environment-specific
secrets.

## Active Examples

- [FortiStore Injection](../chatbot/scenarios/examples/fortistore-injection/README.md)
- [HR Tool DLP](../chatbot/scenarios/examples/hr-tool-dlp/README.md)

These are the only active, validated baseline examples. The catalog lists the
six preserved future candidates without treating them as validated scenarios.
