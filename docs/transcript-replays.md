# Transcript Replays

Transcript replays are preconstructed OpenAI-compatible requests for raw
FortiAIGate and LiteLLM diagnostics. They contain synthetic `assistant` tool
calls and `tool` results that would normally be created during a live chatbot
conversation.

They are requests, not captured outputs. Sending one does not execute the
chatbot, MCP transport, MCP server, upload simulation, document read, or tool.
Use [Functional Validation](functional-validation.md) as the
authoritative end-to-end validation.

## Active Replay Fixtures

| Scenario | Clean boundary | Attack boundary |
|---|---|---|
| HR Tool DLP | [`clean-transcript.json`](../chatbot/scenarios/examples/hr-tool-dlp/transcript-replays/clean-transcript.json) | [`attack-transcript.json`](../chatbot/scenarios/examples/hr-tool-dlp/transcript-replays/attack-transcript.json) |
| Resume Tool Injection | [`clean-transcript.json`](../chatbot/scenarios/examples/resume-tool-injection/transcript-replays/clean-transcript.json) | [`attack-transcript.json`](../chatbot/scenarios/examples/resume-tool-injection/transcript-replays/attack-transcript.json) |

FortiStore Injection has no replay because its primary attack is an ordinary
user prompt plus optional frontend instructions. Candidate and archived
`curl-payloads/` folders remain untouched reference material and are not part
of the validated runtime.

## Diagnostic Boundary

The HR attack replay contains a condensed preconstructed
`employee_table_with_cc` result. It exercises the output-DLP boundary used by
the current Deny and Redact validation cases.

The Resume attack replay ends immediately after the poisoned
`document_read` result. The cloud tool remains declared but has not been
called; this is the input boundary where Alert should allow another model
round and Deny should block it.

## Direct-Flow Contract

When used as a raw diagnostic, send the JSON from the operator shell directly
to the selected scenario flow's `/chat/completions` URL. The body uses the
scenario alias and is shaped like a chatbot request, but it must not be
described as originating from the chatbot.

Supported user-facing curl templates live under each validated scenario's
`functional-tests/` directory and are checked against the same validation
metadata. `python3 -m functional_test render-curl` inserts required frontend
instructions and emits the direct FortiAIGate flow command. Use
`python3 -m functional_test validate` for live pass/fail validation and these
replays only for focused guard inspection.
