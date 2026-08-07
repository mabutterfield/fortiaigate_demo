# Developer Dashboard Workloads

This developer-focused package owns FAIG path traffic and long-running local
dashboard workload generation. Supported scenario validation has the separate
operator-facing entry point `python3 -m functional_test`.

Commands:

```bash
python3 -m load_test paths --help
python3 -m load_test run --help
```

Generated plans, events, checkpoints, GPU samples, and statistics belong under
the ignored `load_test/output/` directory. Tracked workload profiles, prompt
sets, and schemas will remain inside this package.

`prompts/high-token-benign.json` owns tunable long-response passthrough prompts;
these prompts intentionally avoid scenario-attack language.

`profiles/dashboard-balanced-24h.json` owns the default variable 24-hour
schedule. `schemas/dashboard-workload-v1.schema.json` documents its contract.
The runner keeps the 75/25 normal-to-suspicious mix as a long-run baseline,
not an exact hourly quota, and guarantees hourly Alert, Deny, and Redact cases.

Runtime modules are intentionally separated:

- `scenario_validation.py`: shared validation implementation behind the public
  `functional_test` facade; retained here to avoid duplicating result logic
- `workload.py`: reproducible hourly request planning
- `dashboard_runner.py`: bounded scheduling and graceful process lifecycle
- `statistics.py`: atomic progress, result, latency, token, and GPU rollups
- `gpu_monitor.py`: isolated persistent `nvidia-smi` sampling
- `traffic_generator.py`: shared request transport and lightweight path checks
