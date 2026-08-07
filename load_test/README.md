# Developer Load Generator

`load_test` creates bounded synthetic traffic for FortiAIGate dashboard and
performance demonstrations. It is a developer/maintainer tool, not an
installation-readiness check. Operators validate scenarios with
`python3 -m functional_test validate`.

Commands:

```bash
python3 -m load_test paths --help
python3 -m load_test run --help
```

`python3 -m load_test validate` remains only as a compatibility alias to the
functional validator.

The tracked `profiles/dashboard-balanced-24h.json` workload uses a configurable
75/25 normal-to-suspicious long-run baseline, hourly request-volume variance,
and at least one Alert, Deny, and Redact request per hour. High-token benign
passthrough prompts live in `prompts/high-token-benign.json`.

Runs are bounded by duration, hourly volume, and concurrency. The runner
handles `SIGINT` and `SIGTERM`, stops scheduling, drains active work for the
configured grace period, and atomically writes checkpoints and statistics.
Avoid `kill -9` when recoverable final output matters.

Output belongs under ignored `load_test/output/`. Statistics include request
outcomes, expected-over-total results, approximate tokens, latency, GPU
utilization/memory/power/temperature/energy from `nvidia-smi`, and any GPU
collection error. FortiAIGate remains authoritative for dashboard tokens,
demonstration cost, and security outcomes; local token counts are estimates
and displayed cost does not represent actual local-model spend.

See [Developer Load Testing](../docs/development/load-testing.md) for planning,
execution, calibration, output, safe shutdown, and interpretation.
