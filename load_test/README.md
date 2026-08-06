# Local Validation And Dashboard Workloads

This package owns live Phase 11 scenario validation, FAIG path checks, and
long-running local workload generation. It is separate from `tests/`, which
contains fast offline unit and schema tests.

Commands:

```bash
python3 -m load_test validate --help
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

- `scenario_validation.py`: metadata case planning and deployed behavior checks
- `workload.py`: reproducible hourly request planning
- `dashboard_runner.py`: bounded scheduling and graceful process lifecycle
- `statistics.py`: atomic progress, result, latency, token, and GPU rollups
- `gpu_monitor.py`: isolated persistent `nvidia-smi` sampling
- `traffic_generator.py`: shared request transport and lightweight path checks
