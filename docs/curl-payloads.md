# Curl Payload Replay

Status: Phase 10 transitional reference.

Scenario curl payloads simulate MCP tool transcripts inside a single
OpenAI-compatible chat-completions request. They do not call the chatbot agent
or the MCP server. Use them for isolated LiteLLM, FortiAIGate, and model
handling tests.

Current candidate payloads live under:

```text
chatbot/scenarios/examples/<scenario-id>/curl-payloads/
```

Archived payloads live under:

```text
archived_scenarios/<scenario-id>/curl-payloads/
```

## Send One Payload

Set the target endpoint and key:

```bash
export FAIG_URL="http://<faig-host-or-ip>"
export FAIG_API_KEY="<faig-api-key>"
```

Replay through the detect-only compatibility FAIG route:

```bash
curl -sS "$FAIG_URL/v1/demo-a/chat/completions" \
  -H "Authorization: Bearer $FAIG_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @- \
  < chatbot/scenarios/examples/resume-prompt-injection/curl-payloads/attack-tool-result.json
```

Replay through direct LiteLLM:

```bash
export LITELLM_URL="http://<litellm-host-or-ip>:4000"
export LITELLM_API_KEY="<litellm-master-key>"

curl -sS "$LITELLM_URL/v1/chat/completions" \
  -H "Authorization: Bearer $LITELLM_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @- \
  < chatbot/scenarios/examples/resume-prompt-injection/curl-payloads/attack-tool-result.json
```

The same payload body can be used against Direct, FAIG Scan, and FAIG Protect.
Only the URL and key change.

## Payload Index

Most scenario payload folders have two payloads:

| File | Purpose |
|---|---|
| `clean-tool-result.json` | Baseline response with expected tool data. |
| `attack-tool-result.json` | Boundary, DLP, prompt-injection, or tool-misuse path. |

Current active/candidate payload folders:

| Scenario | Payload folder |
|---|---|
| `hr-tool-dlp` | `chatbot/scenarios/examples/hr-tool-dlp/curl-payloads/` |
| `fortistore-injection` | active; no curl payloads currently tracked |
| `fortigate-operator` | `chatbot/scenarios/examples/fortigate-operator/curl-payloads/` |
| `resume-screening-clean` | `chatbot/scenarios/examples/resume-screening-clean/curl-payloads/` |
| `resume-prompt-injection` | `chatbot/scenarios/examples/resume-prompt-injection/curl-payloads/` |
| `resume-cloud-tool-pivot` | `chatbot/scenarios/examples/resume-cloud-tool-pivot/curl-payloads/` |
| `resume-cloud-tool-pivot-safe` | `chatbot/scenarios/examples/resume-cloud-tool-pivot-safe/curl-payloads/` |
| `resume-cloud-tool-pivot-vulnerable` | `chatbot/scenarios/examples/resume-cloud-tool-pivot-vulnerable/curl-payloads/` |

Archived payload folders:

| Scenario | Payload folder |
|---|---|
| `fastfood-ordering` | `archived_scenarios/fastfood-ordering/curl-payloads/` |
| `fortistore-product-advisor` | archived; no curl payloads currently tracked |
| `hr-policy-risk` | `archived_scenarios/hr-policy-risk/curl-payloads/` |
| `hr-policy-rag-risk` | `archived_scenarios/hr-policy-rag-risk/curl-payloads/` |
| `menu-poisoning` | `archived_scenarios/menu-poisoning/curl-payloads/` |
| `support-ticket-triage` | `archived_scenarios/support-ticket-triage/curl-payloads/` |

## Important Limits

- These payloads spoof MCP-like tool results in the LLM transcript.
- They do not prove that the real MCP server returned the data.
- They do not exercise the chatbot MCP tool-profile filter.
- They do not exercise FortiWeb MCP proxy behavior.
- They are useful for isolated FortiAIGate input/output guard testing because
  the tool result is already present in the request body sent to the LLM path.

Phase 11 should regenerate this page around scenario-owned paths after the
scenario matrix architecture lands.
