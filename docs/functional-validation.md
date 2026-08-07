# Functional Validation

Functional validation is the supported post-installation check for
FortiAIGate passthrough and every installed scenario. It uses the deployed
chatbot agent, installed scenario matrix, live MCP transport, and the expected
results declared in each scenario's `validation.cases`.

This is different from repository unit tests, which verify code and metadata
without contacting the deployment, and developer load testing, which creates
bounded dashboard traffic rather than proving installation readiness.

All commands run from `<repo_root>`.

## Prerequisites

- LiteLLM, chatbot, and required MCP components are ready.
- Installed scenario packages match the version you intend to test.
- Required FortiAIGate guards and wildcard flows from the generated work order
  are deployed.
- The workstation can SSH to the selected k3s inventory host.

Select the deployment:

```bash
export FAIG_INVENTORY=local
export FAIG_HOST_ALIAS=jarvis
# or
export FAIG_INVENTORY=cloud
export FAIG_HOST_ALIAS=faig-aws
```

Replace the local host alias when local setup selected another name.

## Validate The Complete Installation

Run passthrough and all declared cases for every installed scenario:

```bash
python3 -m functional_test validate \
  --inventory "$FAIG_INVENTORY" \
  --host-alias "$FAIG_HOST_ALIAS"
```

The validator checks:

- expected completion, block, redaction, sensitive result, or synthetic tool
  pivot;
- every required MCP tool;
- absence of every forbidden tool;
- Resume Deny enforcement before `cloud_bucket_list_demo` executes;
- effective FAIG route, model alias, MCP transport, tool profile, and frontend
  instruction profile; and
- global passthrough without scenario MCP tools.

Each path prints `expected results / total results`. A fully successful run
ends with:

```text
INSTALLATION READY: <expected>/<total> expected results
```

Any unexpected result returns a nonzero exit code and prints missing tools,
forbidden tools, disposition mismatches, or the saved agent-probe error.

## Troubleshooting Filters

Restrict by installed scenario:

```bash
python3 -m functional_test validate \
  --inventory "$FAIG_INVENTORY" \
  --host-alias "$FAIG_HOST_ALIAS" \
  --scenario-id hr-tool-dlp
```

Restrict further by action or exact case:

```bash
python3 -m functional_test validate \
  --inventory "$FAIG_INVENTORY" \
  --host-alias "$FAIG_HOST_ALIAS" \
  --scenario-id hr-tool-dlp \
  --action redact

python3 -m functional_test validate \
  --inventory "$FAIG_INVENTORY" \
  --host-alias "$FAIG_HOST_ALIAS" \
  --scenario-id resume-tool-injection \
  --case deny-attack
```

Action and case filters omit passthrough so the run stays focused. Use
`--skip-passthrough` to omit it from an otherwise unfiltered run. Override MCP
transport, tool profile, or frontend profile only for deliberate Advanced-mode
troubleshooting; the normal run uses the installed Simplified profile.

Preview planned cases without contacting the deployment:

```bash
python3 -m functional_test validate \
  --inventory "$FAIG_INVENTORY" \
  --host-alias "$FAIG_HOST_ALIAS" \
  --dry-run
```

## Output And Evidence

Each run writes to:

```text
functional_test/output/all-scenarios/<run-label>/
```

The ignored output contains one request/response/event capture per case and a
`summary.json`. Events record scenario, action, validation case, generated
route, model alias, MCP transport, tool profile, frontend profile, expected
and actual result, observed/required/forbidden tools, and failure details.

Correlate its UTC timestamps with FortiAIGate traffic logs. Review captures
before sharing because they may contain local endpoints and synthetic attack
or DLP values. Never commit credentials or environment-specific captures.

## Render A Direct-Flow Curl Test

Each validated scenario stores metadata-checked request templates in its
`functional-tests/` directory. Render one installed case:

```bash
python3 -m functional_test render-curl \
  --scenario hr-tool-dlp \
  --action redact \
  --case redact-attack
```

The command writes a JSON body under
`functional_test/output/rendered-curl/`, prints the exact scenario request
path, and emits a curl command using `$FAIG_BASE_URL`:

```bash
export FAIG_BASE_URL=https://<fortiaigate-host>
```

Normal lab flows disable client API-key validation, so generated curl omits
authorization. For an explicitly authenticated flow:

```bash
python3 -m functional_test render-curl \
  --scenario hr-tool-dlp \
  --action redact \
  --case redact-attack \
  --authenticated
```

That variant adds `Authorization: Bearer $FAIG_API_KEY`. Keep the actual key
only in ignored local configuration and never paste it into a template,
screenshot, transcript, or committed shell history.

The generated request goes directly from the operator shell to the selected
FortiAIGate flow. It looks like the OpenAI-compatible LLM request the chatbot
would submit and includes selected frontend instructions, but it does not
claim chatbot origin.

## What Curl Does Not Prove

A direct curl request or transcript replay can deterministically exercise a
FAIG/LiteLLM guard boundary. A single request cannot prove:

- Simplified profile selection in the chatbot UI;
- live MCP schema discovery or tool execution;
- FortiWeb MCP transport;
- multiple model/tool rounds; or
- stop-before-tool enforcement across a live agent loop.

Use the live `validate` command for those assertions. Transcript replays are
described separately in [Transcript Replays](transcript-replays.md).

## Failure Order

When a case fails:

1. compare the generated path, flow, guard, and model alias with the work
   order;
2. confirm the flow is deployed and client API-key validation matches the
   request;
3. test the guard in the FortiAIGate GUI;
4. confirm the installed chatbot profile resolves the expected MCP transport,
   tool profile, and frontend profile;
5. inspect the saved tool sequence and failure details; and
6. correlate the case timestamp with FortiAIGate telemetry.

See [Troubleshooting](troubleshooting.md#functional-scenario-validation-fails)
for component probes.
