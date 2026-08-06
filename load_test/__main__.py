#!/usr/bin/env python3
"""Command dispatcher for local FAIG validation and workload generation."""

from __future__ import annotations

import sys

from load_test import dashboard_runner, scenario_validation, traffic_generator


USAGE = """usage: python3 -m load_test <command> [options]

commands:
  validate  Run live scenario validation through the deployed chatbot
  paths     Send one lightweight request to each installed FAIG path
  run       Generate a scheduled local dashboard workload

Run `python3 -m load_test <command> --help` for command options.
"""


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print(USAGE)
        return 0
    command = sys.argv[1]
    remaining = sys.argv[2:]
    if command == "validate":
        sys.argv = [f"{sys.argv[0]} validate", *remaining]
        return scenario_validation.main()
    if command in {"paths", "run"}:
        if command == "run":
            sys.argv = [f"{sys.argv[0]} run", *remaining]
            return dashboard_runner.main()
        sys.argv = [f"{sys.argv[0]} paths", "--mode", "path_test", *remaining]
        return traffic_generator.main()
    print(f"Unknown load_test command: {command}\n\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
