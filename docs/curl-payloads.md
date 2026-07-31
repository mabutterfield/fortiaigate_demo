# Curl Payload Replay

Each tracked scenario includes curl-ready OpenAI chat-completions payloads under:

```text
chatbot/scenarios/examples/<scenario-id>/curl-payloads/
```

The payloads simulate an MCP tool transcript inside a single LLM request. They
do not call the chatbot agent or the MCP server. Each file includes:

- a scenario system instruction marker
- a user prompt
- a spoofed assistant `tool_calls` message
- one or more raw `role: tool` results
- compact tool schemas in `tools`

This is useful for testing how LiteLLM, FortiAIGate, and the selected model
handle tool-result-like content. It is not a substitute for end-to-end MCP
server, chatbot, or FortiWeb MCP testing.

## Send One Payload

Set the target endpoint and key:

```bash
export FAIG_URL="http://<faig-host-or-ip>"
export FAIG_API_KEY="<faig-api-key>"
```

Replay through the detect-only FAIG route:

```bash
curl -sS "$FAIG_URL/v1/demo-a/chat/completions" \
  -H "Authorization: Bearer $FAIG_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @- \
  < chatbot/scenarios/examples/hr-tool-dlp/curl-payloads/attack-tool-result.json
```

Replay through the protect FAIG route:

```bash
curl -sS "$FAIG_URL/v1/demo-b/chat/completions" \
  -H "Authorization: Bearer $FAIG_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @- \
  < chatbot/scenarios/examples/hr-tool-dlp/curl-payloads/attack-tool-result.json
```

Replay through direct LiteLLM:

```bash
export LITELLM_URL="http://<litellm-host-or-ip>:4000"
export LITELLM_API_KEY="<litellm-master-key>"

curl -sS "$LITELLM_URL/v1/chat/completions" \
  -H "Authorization: Bearer $LITELLM_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @- \
  < chatbot/scenarios/examples/hr-tool-dlp/curl-payloads/attack-tool-result.json
```

The same payload body can be used against Direct, FAIG Scan, and FAIG Protect.
Only the URL and key change.

## Payload Index

Every scenario has two payloads:

| File | Purpose |
|---|---|
| `clean-tool-result.json` | Baseline response with expected tool data. |
| `attack-tool-result.json` | Boundary, DLP, prompt-injection, or tool-misuse path. |

Active scenario payload folders:

| Scenario | Payload folder |
|---|---|
| `hr-tool-dlp` | `chatbot/scenarios/examples/hr-tool-dlp/curl-payloads/` |

Inactive legacy and in-progress scenario payload folders remain in place for
reference and can be used after reactivating the scenario in
`chatbot/scenarios/examples/catalog.json`:

| Scenario | Payload folder |
|---|---|
| `fastfood-ordering` | `chatbot/scenarios/examples/fastfood-ordering/curl-payloads/` |
| `menu-poisoning` | `chatbot/scenarios/examples/menu-poisoning/curl-payloads/` |
| `hr-policy-risk` | `chatbot/scenarios/examples/hr-policy-risk/curl-payloads/` |
| `hr-policy-rag-risk` | `chatbot/scenarios/examples/hr-policy-rag-risk/curl-payloads/` |
| `resume-screening-clean` | `chatbot/scenarios/examples/resume-screening-clean/curl-payloads/` |
| `resume-prompt-injection` | `chatbot/scenarios/examples/resume-prompt-injection/curl-payloads/` |
| `resume-cloud-tool-pivot-safe` | `chatbot/scenarios/examples/resume-cloud-tool-pivot-safe/curl-payloads/` |
| `resume-cloud-tool-pivot-vulnerable` | `chatbot/scenarios/examples/resume-cloud-tool-pivot-vulnerable/curl-payloads/` |
| `resume-cloud-tool-pivot` | `chatbot/scenarios/examples/resume-cloud-tool-pivot/curl-payloads/` |
| `support-ticket-triage` | `chatbot/scenarios/examples/support-ticket-triage/curl-payloads/` |
| `fortigate-operator` | `chatbot/scenarios/examples/fortigate-operator/curl-payloads/` |

## Important Limits

- These payloads spoof MCP-like tool results in the LLM transcript.
- They do not prove that the real MCP server returned the data.
- They do not exercise the chatbot MCP tool-profile filter.
- They do not exercise FortiWeb MCP proxy behavior.
- They are useful for isolated FortiAIGate input/output guard testing because
  the tool result is already present in the request body sent to the LLM path.
