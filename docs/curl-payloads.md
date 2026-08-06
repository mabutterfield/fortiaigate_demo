# Curl Payload Replay

Status: Phase 11 scenario-owned reference.

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

Replay through the Resume Tool Injection Alert route:

```bash
curl -sS "$FAIG_URL/v1/resume-tool-injection/alert/chat/completions" \
  -H "Authorization: Bearer $FAIG_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @- \
  < chatbot/scenarios/examples/resume-tool-injection/curl-payloads/attack-tool-result.json
```

Replay the same transcript through Deny:

```bash
curl -sS "$FAIG_URL/v1/resume-tool-injection/deny/chat/completions" \
  -H "Authorization: Bearer $FAIG_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @- \
  < chatbot/scenarios/examples/resume-tool-injection/curl-payloads/attack-tool-result.json
```

Replay through direct LiteLLM:

```bash
export LITELLM_URL="http://<litellm-host-or-ip>:4000"
export LITELLM_API_KEY="<litellm-master-key>"

curl -sS "$LITELLM_URL/v1/chat/completions" \
  -H "Authorization: Bearer $LITELLM_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @- \
  < chatbot/scenarios/examples/resume-tool-injection/curl-payloads/attack-tool-result.json
```

The same payload body can be used against Direct, Alert, and Deny. Only the URL
and key change.

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
| `resume-tool-injection` | `chatbot/scenarios/examples/resume-tool-injection/curl-payloads/` |

Archived payload folders:

| Scenario | Payload folder |
|---|---|
| `fastfood-ordering` | `archived_scenarios/fastfood-ordering/curl-payloads/` |
| `fortistore-product-advisor` | archived; no curl payloads currently tracked |
| `hr-policy-risk` | `archived_scenarios/hr-policy-risk/curl-payloads/` |
| `hr-policy-rag-risk` | `archived_scenarios/hr-policy-rag-risk/curl-payloads/` |
| `menu-poisoning` | `archived_scenarios/menu-poisoning/curl-payloads/` |
| `support-ticket-triage` | `archived_scenarios/support-ticket-triage/curl-payloads/` |
| `resume-screening-clean` | `archived_scenarios/resume-screening-clean/curl-payloads/` |
| `resume-prompt-injection` | `archived_scenarios/resume-prompt-injection/curl-payloads/` |
| `resume-cloud-tool-pivot` | `archived_scenarios/resume-cloud-tool-pivot/curl-payloads/` |
| `resume-cloud-tool-pivot-safe` | `archived_scenarios/resume-cloud-tool-pivot-safe/curl-payloads/` |
| `resume-cloud-tool-pivot-vulnerable` | `archived_scenarios/resume-cloud-tool-pivot-vulnerable/curl-payloads/` |

## Important Limits

- These payloads spoof MCP-like tool results in the LLM transcript.
- They do not prove that the real MCP server returned the data.
- They do not exercise the chatbot MCP tool-profile filter.
- They do not exercise FortiWeb MCP proxy behavior.
- They are useful for isolated FortiAIGate input/output guard testing because
  the tool result is already present in the request body sent to the LLM path.
- The attack replay already contains an assistant cloud-tool request and its
  synthetic result. It can prove transcript inspection, but it cannot prove
  that Deny stopped a live MCP call. Use `python3 -m load_test validate` and inspect
  the actual tool sequence for the end-to-end enforcement test.
