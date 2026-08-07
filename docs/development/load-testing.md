# Developer Load Testing

The load generator creates synthetic dashboard volume after functional
validation already passes. It is intended for developers and demo maintainers
who need request, outcome, token, cost, latency, and GPU trends. It is not part
of quickstart, scenario setup, or presenter validation.

All commands run from `<repo_root>`. Review the plan before sending traffic.

## Safety And Cost Boundary

The tracked workload targets local models, so token use does not incur a
per-token provider bill. It still consumes electricity, GPU time, storage, and
operator attention. FortiAIGate demonstration cost is configured per guard to
show the dashboard feature and is not an accounting record.

Keep duration, hourly volume, maximum concurrency, token request size, and
target environment bounded. Do not point the default high-token profile at a
paid provider without reviewing and changing it first.

## Preflight

1. Run [Functional Validation](../functional-validation.md) and resolve every
   unexpected scenario result.
2. Confirm the target inventory and host alias.
3. Confirm all installed scenario paths exist in FortiAIGate.
4. Verify available disk space under `load_test/output/`.
5. Preview the exact request plan.

```bash
python3 -m load_test run --dry-run
```

## Workload Contract

The default profile is
`load_test/profiles/dashboard-balanced-24h.json`:

- 24-hour planned duration;
- 12–30 requests per hour using a bounded random walk;
- 75% normal and 25% suspicious traffic as a configurable long-run baseline;
- natural hourly variance rather than an exact per-hour ratio;
- at least one Alert, Deny, and Redact request each hour;
- benign passthrough prompts requesting approximately 800–1,600 output words;
- at most four active requests;
- statistics updates every 30 seconds;
- recoverable checkpoints every 60 seconds; and
- NVIDIA samples every five seconds.

Protected requests are selected from installed scenario
`validation.cases`. Normal prompts come from
`load_test/prompts/high-token-benign.json` and intentionally avoid attack
language.

Tune a copied local profile rather than silently changing the tracked release
baseline. Keep local experiments ignored.

## Calibration

Run a one-hour calibration before a 24-hour workload:

```bash
python3 -m load_test run \
  --hours 1 \
  --label dashboard-one-hour
```

The command prints its plan and requires confirmation before sending traffic.
Use `--yes` only after reviewing the target and bounds.

Run the tracked full profile:

```bash
python3 -m load_test run --yes
```

Multiple requests may run concurrently up to the profile limit. Sequential
scenario execution is easier to diagnose; bounded parallel execution creates
more realistic latency and utilization trends.

## Lightweight Path Probe

The developer path probe sends one basic request to each generated FAIG route:

```bash
python3 -m load_test paths \
  --path-test-execution chatbot-pod \
  --inventory local \
  --host-alias jarvis
```

This is useful for traffic plumbing but does not replace semantic functional
validation of Deny, Redact, or MCP tool traces.

## Output

Each run writes an ignored directory:

```text
load_test/output/runs/<run-label>/
├── plan.json
├── events.jsonl
├── gpu.jsonl
├── statistics.json
├── checkpoint.json
└── summary.json
```

`statistics.json` is replaced atomically and periodically. It reports:

- planned, submitted, active, completed, and remaining requests;
- success, alert, deny, redact, and error outcomes;
- suspicious versus normal requests;
- expected results over total results per path;
- approximate input, output, and total tokens;
- minimum, maximum, and average latency; and
- GPU utilization, memory, power, temperature, and estimated energy.

Token estimates use roughly four characters per token. Compare dashboard
tokens and configured cost trends in FortiAIGate rather than expecting the
local estimate to match exactly.

## NVIDIA Metrics

The sampler invokes `nvidia-smi` and records persistent samples when the
installed driver exposes utilization, memory, power, and temperature. There is
no separate universal performance-counter store required by the generator.
Missing `nvidia-smi`, unsupported fields, or collection failure is recorded in
statistics and does not stop request traffic.

## Safe Interruption

Use Ctrl-C or normal `kill <pid>`. On `SIGINT` or `SIGTERM`, the runner:

1. stops scheduling new work;
2. drains active requests for the configured grace period;
3. stops GPU sampling; and
4. atomically flushes statistics, checkpoint, and summary output.

Use `kill -9` only when the process cannot shut down normally; it can prevent a
final checkpoint.

## Interpretation

Use FortiAIGate for authoritative request outcomes, tokens, configured demo
cost, and traffic trends. Use the local statistics for workload progress,
expected-result health, approximate volume, client-observed latency, and GPU
behavior. Investigate errors or unexpected security results with the
functional validator before increasing traffic.
