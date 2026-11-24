# Shared FortiAIGate Agent Loop

`faig_agent.py` runs one agent turn for FortiAIGate 8.0.2 lab clients: it sends
the conversation to an OpenAI-compatible endpoint, offers the scenario's tools
from the standards MCP endpoint, executes tool calls over MCP, and loops until
the model answers or the round limit is reached.

It is shared so the student chatbot and the command-line checks exercise the
same logic:

- the 8.0.2 lab chatbot imports it for chat, **Try a prompt** and graded
  tests (`deploy_lab_chatbot.yml` copies it into the chart; see
  [Lab Chatbot](../../docs/lab-chatbot.md));
- `functional_test catalog-baseline` and `functional_test baseline` stage it
  into the MCP pod with `functional_test/baseline_agent.py`.

The scenario's model alias, tools and round limit come from the 8.0.2 catalog
(`catalog802/`); see [Scenario Management](../../docs/scenario-management.md).

Endpoints:

| Mode | `base_url` | Key |
|---|---|---|
| FortiAIGate | `https://ingress-nginx-controller.ingress-nginx.svc.cluster.local/ai/openai/v1` (HTTPS since 2026-11-20; plain HTTP is redirected; pass `verify_tls: false` for the self-signed lab certificate) | student virtual key for the scenario action |
| Direct | `http://litellm.litellm.svc.cluster.local:4000/v1` | shared non-admin LiteLLM virtual key |

`record_exchanges` adds every request body and response to the result for the
single-test view. Keys are sent only in the `Authorization` header and never
appear in results or exchanges. See the module docstring for all spec and
result fields; `tests/test_faig_agent.py` covers the loop with a fake endpoint
and MCP session.
