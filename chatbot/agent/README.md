# Shared FortiAIGate Agent Loop

`faig_agent.py` runs one agent turn for FortiAIGate 8.0.2 lab clients: it sends
the conversation to an OpenAI-compatible endpoint, offers the scenario's tools
from the standards MCP endpoint, executes tool calls over MCP, and loops until
the model answers or the round limit is reached.

It is shared so the validation baseline and the student chatbot exercise the
same logic:

- `functional_test baseline` stages it into the MCP pod with
  `functional_test/baseline_agent.py`;
- the 8.0.2 student chatbot imports it (planned).

Endpoints:

| Mode | `base_url` | Key |
|---|---|---|
| FortiAIGate | `http://ingress-nginx-controller.ingress-nginx.svc.cluster.local/ai/openai/v1` | student virtual key for the scenario action |
| Direct | `http://litellm.litellm.svc.cluster.local:4000/v1` | shared non-admin LiteLLM virtual key |

`record_exchanges` adds every request body and response to the result for the
single-test view. Keys are sent only in the `Authorization` header and never
appear in results or exchanges. See the module docstring for all spec and
result fields; `tests/test_faig_agent.py` covers the loop with a fake endpoint
and MCP session.
