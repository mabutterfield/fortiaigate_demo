# Scenario Authoring

This guide owns the technical contract for creating, changing, documenting,
and promoting scenario packages. Use [Scenario Management](scenario-management.md)
for the operator install lifecycle and the
[Scenario Catalog](../chatbot/scenarios/examples/scenario-catalog.md) for
validated, candidate, and archived classification.

All commands run from `<repo_root>`.

## Ownership And Lifecycle

| Content | Location | Ownership |
|---|---|---|
| Built-in or candidate source | `chatbot/scenarios/examples/<scenario-id>/` | Tracked, read-only installation source |
| Installed scenario | `chatbot/scenarios/local/<scenario-id>/` | Git-ignored, operator-editable runtime copy |
| Archived scenario | `archived_scenarios/<scenario-id>/` | Tracked historical/reference content |
| Generated work order | `docs/raw-output/scenario-work-orders/` | Git-ignored, installation-specific |
| Functional evidence | `functional_test/output/` | Git-ignored test capture |

Tune the installed copy first. Promote generally useful changes back to a
tracked candidate or built-in only after review. A repository pull never
overwrites installed content; `update --force` creates a backup before an
explicit replacement.

## Package Structure

```text
chatbot/scenarios/examples/<scenario-id>/
├── profile.json
├── instructions.txt
├── README.md
├── optional frontend-*.instructions.txt
├── functional-tests/
│   ├── cases.json
│   └── one or more request templates
├── optional transcript-replays/
└── optional images/
```

`profile.json` uses
`chatbot/scenarios/scenario-profile-v2.schema.json`. The scenario validator
also enforces semantic relationships that JSON Schema alone cannot express.

Scenario IDs are lowercase kebab-case and become the LiteLLM model alias. Use
`<concept>-[tool]-<type>` when tool use is central, for example
`fortistore-injection`, `hr-tool-dlp`, or `resume-tool-injection`. Generated
names are:

| Object | Pattern |
|---|---|
| LiteLLM alias | `<scenario-id>` |
| FAIG configured URI | `/v1/<scenario-id>/<action>/*` |
| Flow/route | `<scenario-id>-<action>` |
| Suggested guard | `<scenario-id>_<action>` |
| Extended MCP profile | `<scenario-id>-<tool-set-id>` |

## Backend And Frontend Instructions

`instructions.txt` is loaded by LiteLLM for the scenario alias. State the
assistant role, permitted behavior, synthetic-data boundary, expected tool
selection, and a stable activation marker useful for troubleshooting. Keep
instructions realistic enough for the demo while clearly identifying unsafe
or deliberately vulnerable behavior.

Frontend instruction profiles are chatbot-local system messages. Define them
under `matrix.frontend_instruction_profiles` and reference them from
Simplified profiles. `none` must exist exactly once. Unsafe frontend fixtures
must be labeled as controlled test content and must never contain credentials.

Backend changes require LiteLLM deployment. Frontend file changes require
chatbot deployment but no image rebuild.

## Actions And Guards

Define only actions used by the security story:

| Action | Guard intent |
|---|---|
| `alert` | Detect and record without enforcement; uses `detect_only` |
| `deny` | Block protected input or output; uses `protect_input` or `output_dlp_deny` |
| `redact` | Replace protected output and return the safe remainder; uses `output_dlp_redact` |
| `redact-dummy` | Reserved for a future input-DLP replacement scenario |

`direct` is a chatbot/LiteLLM control, not a FAIG entry point. Every built-in
has one Alert path and only the enforcement actions its story needs.

Record where risky content first appears—user input, conversation context,
tool arguments/results, or model output—because that determines input versus
output protection. For DLP, test both one protected value and a multi-record
response; partial multi-row redaction is not a pass.

## MCP Tool Contract

All scenarios share one MCP service. `mcp.required_tools` creates the base
least-privilege profile. `extended_tool_sets` add named comparison tools, and
`all-installed` is the optional generated cross-domain set. `all-server` is
debug-only and must not appear in a normal Simplified profile.

FortiWeb is the preferred transport when installed, configured, and desired.
Direct MCP is the deterministic fallback and Advanced-mode troubleshooting
choice. Transport selection never expands the tool set.

Record the maximum tool rounds, required tool sequence, and forbidden tools.
For a stop-before-tool test, response wording is insufficient: the forbidden
tool must be absent from the live trace.

## Simplified Profiles

One Simplified profile represents one presenter intent, not every possible
transport combination. It selects provider path, scenario alias and route,
context mode/window, frontend profile, MCP state/transport, tool profile, and
tool-round limit.

Follow the FortiStore display-name convention:

```text
<Scenario Display Name> - LLM Direct
<Scenario Display Name> - Baseline   # only when it is a distinct comparison
<Scenario Display Name> - Alert
<Scenario Display Name> - Redact
<Scenario Display Name> - Deny
```

Advanced mode remains available for intentional transport, frontend, or tool
profile changes.

## FAIG Re-entry

The capability is globally available, while every built-in sets
`matrix.faig_chain.enabled: false`. An operator-owned local scenario may opt
in. The generated `*-faig-chain` alias must re-enter only through global
passthrough and terminate at `pass-model`; never route passthrough back to a
chain alias.

## Prompts And Validation Cases

Keep clean and attack prompts in `profile.json`. Each release-required action
needs a stable `validation.cases` entry with:

- unique case ID;
- action;
- `clean` or `attack` prompt kind and zero-based index;
- expected result;
- required tools; and
- forbidden tools.

Supported expected results are completion, block, redaction, sensitive tool or
model output, and the synthetic resume tool pivot. Prefer observable security
disposition and tool trace over prose matching.

## Functional Curl Templates

Every validation case maps to one request template through
`functional-tests/cases.json`:

```json
{
  "schema_version": 1,
  "cases": {
    "deny-attack": {
      "request": "attack-request.json"
    }
  }
}
```

Templates are OpenAI-compatible request bodies. Their model must equal the
scenario ID, and their messages must contain the exact metadata prompt. Do not
embed frontend instructions: `render-curl` reads the selected installed
frontend profile and inserts it dynamically.

For MCP security boundaries, a template may contain preconstructed synthetic
assistant tool calls and tool results. This makes the request deterministic
but does not claim those tools executed. Keep live agent-loop assertions in
the metadata-driven validator.

Validate and render:

```bash
python3 scripts/scenario_profiles.py validate
python3 -m functional_test render-curl \
  --scenario <scenario-id> \
  --action <action> \
  --case <case-id>
```

## Transcript Replays

`transcript-replays/` contains raw diagnostic requests that are useful beyond
one release case. Name active fixtures `clean-transcript.json` and
`attack-transcript.json`. They are requests with preconstructed tool history,
not outputs and not live MCP tests. Functional curl templates are the
user-facing, metadata-mapped cases; replays are focused diagnostic fixtures.

## README And Evidence Contract

Each scenario README uses this order:

1. security story;
2. simulated-data boundary;
3. prerequisites and install/deploy;
4. generated objects and GUI variables;
5. Simplified and Advanced comparisons;
6. prompt/outcome table and action behavior;
7. headless validation and curl commands; and
8. evidence and troubleshooting.

Use the shared GUI guide and screenshots for common steps. Store at most one
or two scenario-specific images when a shared image cannot explain unique
tuning or evidence. Screenshots must omit credentials, private endpoints,
installation identifiers, and non-synthetic data.

Capture scenario ID, case, action, request path, timestamp, flow, guard, model
alias, MCP transport, tool profile, frontend profile, tool sequence,
detector/action, and final disposition. Review ignored captures before sharing.

## Authoring Workflow

1. Define the smallest security story and simulated-data boundary.
2. Choose actions and the narrowest tool profile.
3. Create or update a candidate package.
4. Validate the schema, semantic contract, curl mappings, and generated matrix.
5. Install an editable copy and tune it locally.
6. Deploy LiteLLM/chatbot and MCP only when its code or fixtures changed.
7. Create FAIG objects from the generated work order.
8. Run the live validator and render each direct-flow curl.
9. capture and review evidence and screenshots.
10. promote to the validated catalog only when every required case is
    repeatable and documentation is current.

```bash
python3 scripts/scenario_profiles.py validate
python3 scripts/scenario_profiles.py add <scenario-id>
python3 scripts/scenario_profiles.py show-matrix
python3 scripts/scenario_profiles.py render-work-order
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/smoke_test.py
python3 -m functional_test validate --scenario-id <scenario-id>
```

## Deploy Boundaries

| Change | Required action |
|---|---|
| Backend instructions/model mapping | Deploy LiteLLM |
| Frontend instructions or generated chatbot profiles/routes | Deploy chatbot |
| Chatbot or agent-probe code | Increment tag, publish image, deploy chatbot |
| MCP code, schema, fixture, or credentials | Deploy MCP |
| Advanced UI selection | No redeploy |
| FAIG entry point | Render work order and update/deploy GUI objects manually |

Removing or updating an installed scenario does not mutate remote FortiAIGate
objects. Reconcile those disposable-lab objects manually.
