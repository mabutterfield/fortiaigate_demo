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
against the inferred FortiAIGate HTTPS endpoint. The tested paths and request
models come from the installed Phase 11 scenario matrix, including canonical
`/v1/passthrough` with `pass-model`:

```bash
python3 scripts/traffic_generator.py
```

Expected output shape:

```text
target: local
target base URL: https://192.168.248.80/v1/
mode: path_test
execution: workstation curl
paths: /v1/fortistore-injection/alert, ..., /v1/hr-tool-dlp/redact, /v1/passthrough
Results:
/v1/fortistore-injection/alert: working (HTTP 200, model=fortistore-injection)
/v1/hr-tool-dlp/alert: working (HTTP 200, model=hr-tool-dlp)
/v1/passthrough: working (HTTP 200, model=pass-model)
```

Use `--path-test-base-url` to test a specific FortiAIGate, FortiGate proxy, or
FortiWeb proxy endpoint. Use `--path-test-execution chatbot-pod` only when you
intentionally want to test from inside the cluster against Kubernetes DNS.

Scenario traffic requires `--mode traffic`. By default it mixes the `direct`
and `alert` actions for each installed baseline scenario. Use `--action` to
select one or more exact scenario roles. The generator resolves each role's
route, model, MCP setting, tool profile, frontend profile, and tool-round limit
from the installed matrix.

Raw prompts and raw responses are not saved by default. The generator writes
compact metadata under ignored `docs/raw-output/traffic/<run-label>/`, including
scenario ID, prompt ID, route, model alias, MCP path, observed tool names,
latency, approximate response length, security disposition, and the agent base
URLs used for the model and MCP calls.

## Scenario Selection

Default scenario selection is `--scenario-source installed`. The generator
reads ignored packages under `chatbot/scenarios/local/`; local prompt tuning is
therefore reflected without changing tracked examples.

| Action | Generated behavior |
|---|---|
| `direct` | Direct LiteLLM with the scenario alias and scenario MCP defaults |
| `alert` | The scenario-owned FAIG detection-and-allow route |
| `deny` | The scenario-owned FAIG denial route |
| `redact` | The scenario-owned FAIG redaction route, when declared |
| `passthrough` | Canonical FAIG bypass using `pass-model`, without scenario instructions or MCP |

This avoids sending a FortiStore prompt to an HR model or an HR tool profile to
a non-MCP scenario. Use one of these forms to narrow the generated mix:

```bash
python3 scripts/traffic_generator.py \
  --mode traffic \
  --scenario-source installed \
  --scenario-family baseline \
  --action direct \
  --dry-run

python3 scripts/traffic_generator.py \
  --mode traffic \
  --scenario fortistore-injection \
  --action direct \
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
  --action alert \
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
  --action direct \
  --dry-run
```

Local burst:

```bash
python3 scripts/traffic_generator.py \
  --mode traffic \
  --target local \
  --use-case burst \
  --scenario fortistore-injection \
  --action direct \
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
  --action direct \
  --allow-cloud-long-run \
  --yes
```

## Actions

| Action | Behavior |
|---|---|
| `direct` | Chatbot to Direct LiteLLM using the scenario alias and MCP defaults. |
| `alert` | Chatbot to the scenario-owned FAIG detection-and-allow route. |
| `deny` | Chatbot to the scenario-owned FAIG denial route. |
| `redact` | Chatbot to the scenario-owned FAIG redaction route, when declared. |
| `passthrough` | Chatbot to canonical `/v1/passthrough` using `pass-model`. |

Repeat `--action` or pass comma-separated actions for a mixed plan:

```bash
python3 scripts/traffic_generator.py \
  --mode traffic \
  --use-case steady \
  --scenario hr-tool-dlp \
  --action direct,alert,redact \
  --dry-run
```

For the advanced MCP alternate, keep the same scenario/action and pass
`--mcp-path fortiweb`. The Phase 10 `--route` and `--scenario-source
active-slot` options remain available only for old demo-slot invocations.

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
