# Local Validation And Dashboard Workload

The dedicated `load_test` package owns live Phase 11 validation, lightweight
path checks, and long-running local traffic used to populate the FortiAIGate
dashboard.

## Commands

Validate every protected path from scenario metadata, plus canonical
passthrough:

```bash
python3 -m load_test validate
```

Send one lightweight OpenAI-compatible request to every installed FAIG path:

```bash
python3 -m load_test paths \
  --path-test-execution chatbot-pod \
  --inventory ansible/inventory/local.generated.ini \
  --host-alias jarvis
```

Preview the default 24-hour dashboard workload without sending traffic:

```bash
python3 -m load_test run --dry-run
```

Run the tracked profile:

```bash
python3 -m load_test run --yes
```

Override its duration for a one-hour calibration:

```bash
python3 -m load_test run \
  --hours 1 \
  --label dashboard-one-hour
```

## Workload Profile

The tracked profile is
`load_test/profiles/dashboard-balanced-24h.json`. Its defaults are:

- 24 hours on the local `jarvis` inventory host
- 12–30 requests per hour using a bounded random walk
- 75% normal traffic as a long-run baseline, with hourly variance
- at least one Alert, Deny, and Redact request every hour
- benign passthrough prompts requesting 800–1,600 output words
- at most four active requests
- statistics updated every 30 seconds and checkpoints every 60 seconds
- NVIDIA GPU samples every five seconds

Normal prompts live in
`load_test/prompts/high-token-benign.json`. Protected requests come from the
machine-readable `validation.cases` in each installed baseline scenario.

## Validation

Each case declares its prompt, action, expected result, required tools, and
forbidden tools. The live validator and dashboard runner use the same case
planner and evaluator. Current expected outcomes include:

| Path | Expected result |
|---|---|
| Alert | Scenario remains deliberately observable/vulnerable as declared |
| Deny | Request or tool response is blocked |
| Redact | Protected HR fields are redacted |
| Resume Deny | Blocked before `cloud_bucket_list_demo` executes |
| Passthrough | Completes without scenario instructions or MCP |

Both commands print and save expected results over total results for each
canonical provider route.

## Output And Statistics

Each run writes under the ignored directory
`load_test/output/runs/<run-label>/`:

```text
plan.json
events.jsonl
gpu.jsonl
statistics.json
checkpoint.json
summary.json
```

`statistics.json` is replaced atomically and includes request outcomes,
approximate input/output tokens, latency, expected-result totals, path results,
and GPU aggregates. Token estimates use roughly four characters per token;
FortiAIGate remains authoritative for its dashboard token and demonstration
cost trends.

GPU telemetry records utilization, memory, power, temperature, and estimated
GPU energy from `nvidia-smi`. GPU collection failure is reported in statistics
but does not stop traffic.

## Safe Shutdown

The runner handles `SIGINT` and `SIGTERM`. It stops scheduling new work, drains
active requests for the configured grace period, stops the GPU sampler, and
atomically flushes statistics, checkpoint, and summary state. Use normal
`kill <pid>` or Ctrl-C; avoid `kill -9` when a clean checkpoint is desired.

## Offline Tests Versus Live Validation

Repository tests under `tests/` validate schemas, profiles, fixtures, matrix
generation, plan construction, expectations, and statistics without contacting
Jarvis. `python3 -m load_test validate` is the deployed behavioral check.
