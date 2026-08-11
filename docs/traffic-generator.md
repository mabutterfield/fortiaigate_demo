# Traffic Generator

`scripts/traffic_generator.py` generates repeatable chatbot/MCP traffic for
demo recording, FortiAIGate dashboard/log population, and local load-style
testing.

The generator has two modes. `path_test` performs a single lightweight
OpenAI-compatible request per FAIG path. `traffic` uses the same deployed
chatbot `agent_probe.py` path as the scenario harness: it SSHes to the k3s host,
runs `kubectl exec` against the chatbot deployment, and exercises the
chatbot-owned MCP agent loop.

With no arguments, the generator runs a direct workstation `curl` path test
against the inferred FortiAIGate HTTPS endpoint. This validates that the three
baseline FAIG paths answer before any scenario traffic is sent:

```bash
python3 scripts/traffic_generator.py
```

Expected output shape:

```text
target: local
target base URL: https://192.168.248.80/v1/
mode: path_test
execution: workstation curl
paths: /v1/demo-a, /v1/demo-b, /v1/passthrough
Results:
/v1/demo-a: working (HTTP 200, model=demo-a)
/v1/demo-b: working (HTTP 200, model=demo-a)
/v1/passthrough: working (HTTP 200, model=pass-ollama)
```

Use `--path-test-base-url` to test a specific FortiAIGate, FortiGate proxy, or
FortiWeb proxy endpoint. Use `--path-test-execution chatbot-pod` only when you
intentionally want to test from inside the cluster against Kubernetes DNS.

Scenario traffic requires `--mode traffic`. It sends FAIG static `demo-a`
traffic (`--route faig-scan`) by default so FortiAIGate logs and dashboards are
populated. Use `--route direct` only when intentionally bypassing FortiAIGate
for a control run.

Raw prompts and raw responses are not saved by default. The generator writes
compact metadata under ignored `docs/raw-output/traffic/<run-label>/`, including
scenario ID, prompt ID, route, model alias, MCP path, observed tool names,
latency, approximate response length, security disposition, and the agent base
URLs used for the model and MCP calls.

## Scenario Selection

Default scenario selection is `--scenario-source active-slot`. The generator
reads the local instruction metadata for the selected route/model and sends the
matching scenario:

| Traffic route | Scenario source |
|---|---|
| `faig-scan` | `chatbot/instructions/local/demo-a/metadata.json` |
| `faig-protect` | `chatbot/instructions/local/demo-a/metadata.json` |
| `direct` | the `--model` slot when it is `demo-a` or `demo-b` |
| `fortigate-litellm` | the `--model` slot when it is `demo-a` or `demo-b` |
| `fortigate-ollama` | `chatbot/instructions/local/demo-a/metadata.json`; backend model is the configured Ollama model, normally `gpt-oss:20b` |
| `fortiweb-mcp` | the `--model` slot when it is `demo-a` or `demo-b` |

This avoids sending a FortiStore prompt to an HR instruction slot, or a DLP
prompt to a product-advisor slot. Inactive catalog entries are ignored by
normal selection. If the local metadata is missing or you intentionally want a
manual mix, use one of these forms:

```bash
python3 scripts/traffic_generator.py \
  --mode traffic \
  --scenario-source family \
  --scenario-family baseline \
  --route direct \
  --dry-run

python3 scripts/traffic_generator.py \
  --mode traffic \
  --scenario fortistore-injection \
  --route direct \
  --dry-run
```

## Use Cases

### Steady Log And Dashboard Population

Use `steady` for persistent but not excessive queries over a long duration.
This is the right mode when the goal is FortiAIGate charts, FortiGate/FortiWeb
logs, and recorded-demo background traffic.

Short dry run:

```bash
python3 scripts/traffic_generator.py \
  --mode traffic \
  --use-case steady \
  --duration 60 \
  --rate 6 \
  --dry-run
```

Long local run:

```bash
python3 scripts/traffic_generator.py \
  --mode traffic \
  --target local \
  --use-case steady \
  --duration 3600 \
  --rate 6 \
  --route faig-scan \
  --label local-dashboard-hour \
  --yes
```

### Burst Load Or DoS-Style Testing

Use `burst` for short but heavy traffic when testing load behavior or
DoS-related protections. Keep this local unless a cloud run is deliberately
approved.

Dry run:

```bash
python3 scripts/traffic_generator.py \
  --mode traffic \
  --use-case burst \
  --scenario fortistore-injection \
  --route direct \
  --dry-run
```

Local burst:

```bash
python3 scripts/traffic_generator.py \
  --mode traffic \
  --target local \
  --use-case burst \
  --scenario fortistore-injection \
  --route direct \
  --label local-burst-test \
  --yes
```

Cloud burst runs require explicit opt-in:

```bash
python3 scripts/traffic_generator.py \
  --mode traffic \
  --target aws \
  --use-case burst \
  --scenario fortistore-injection \
  --route direct \
  --allow-cloud-long-run \
  --yes
```

## Routes

| Route | Behavior |
|---|---|
| `direct` | Chatbot to Direct LiteLLM with the selected MCP path. |
| `fortigate-litellm` | Chatbot to a FortiGate HTTP listener forwarding to LiteLLM with the selected MCP path. Requires `chatbot_fortigate_litellm_base_url`. |
| `fortigate-ollama` | Chatbot to a FortiGate HTTP listener forwarding to Ollama's OpenAI-compatible `/v1` API. Requires `chatbot_fortigate_ollama_base_url`. |
| `faig-scan` | Chatbot to FortiAIGate static `demo-a` route with the selected MCP path. |
| `faig-protect` | Chatbot to FortiAIGate static `demo-b` route with the selected MCP path. The manual FAIG mapping should point this Demo-B entry point at LiteLLM `demo-a` so only the FAIG guard changes. |
| `fortiweb-mcp` | Chatbot to Direct LiteLLM with FortiWeb-fronted MCP. |

Repeat `--route` or pass comma-separated routes for a mixed route plan:

```bash
python3 scripts/traffic_generator.py \
  --mode traffic \
  --use-case steady \
  --route direct,faig-scan,faig-protect \
  --scenario-source family \
  --scenario-family baseline \
  --dry-run
```

The direct and MCP internal paths use Kubernetes DNS by default, for example
`litellm.litellm.svc.cluster.local` and
`mcp-demo.mcp.svc.cluster.local`. FAIG static routes use the configured
in-cluster ingress DNS name, normally
`ingress-nginx-controller.ingress-nginx.svc.cluster.local`. The compact event
metadata records `agent_base_url` and `agent_mcp_base_url` so each run shows
which DNS name or IP address the deployed chatbot actually used.

If the deployed chatbot image is older than the local repo and its
`/app/agent_probe.py` does not support `--tool-profile`, the generator omits
that option and prints a warning. The request still runs, but the chatbot's
default MCP tool profile controls which tools are visible until the chatbot is
redeployed.

## Security Dispositions

Protected routes may block or redact some requests. That is expected for
prompt-injection, DLP, MCP, and DoS-style tests.

The generator treats successful agent responses as completed requests and adds
a `security_disposition` field:

| Disposition | Meaning |
|---|---|
| `allowed` | The response did not include known block/redaction markers. |
| `blocked` | The response appears to have been denied or blocked by policy. |
| `redacted` | The response appears to have masked or redacted sensitive content. |
| `unknown` | The request failed before a normal agent response was available. |

Transport failures, SSH failures, invalid JSON from `agent_probe.py`, and pod
execution failures are still counted as errors.

## Safeguards

- Default target is `local`.
- Default mode is `path_test`, which sends one lightweight request to each
  baseline FAIG path.
- Traffic mode defaults to the `steady` use case with a short 60-second,
  low-rate run.
- Public/cloud long runs require `--allow-cloud-long-run`.
- Long or high-request local runs require `--yes` in non-interactive shells.
- Concurrency is capped at `4`.
- Unknown scenarios or routes fail before traffic is sent.
- Raw prompts and responses are not saved by default.
- Output stays under ignored `docs/raw-output/traffic/`.

## Output

Default output:

```text
docs/raw-output/traffic/<run-label>/
  plan.json
  events.jsonl
  summary.json
```

Use `--summary-only` to skip `events.jsonl`.

`summary.json` includes request counts, latency summary, observed tool counts,
security disposition counts, and error counts. `events.jsonl` contains one
compact metadata object per completed request.
