#!/usr/bin/env python3
"""Run supported FAIG functional validation from repository metadata."""

from __future__ import annotations

import sys

USAGE = """usage: python3 -m functional_test <command> [options]

Choose a command explicitly.

commands:
  catalog-baseline  Run one live catalog case and verify its Traffic Log
  evaluate-catalog  Evaluate saved observations against a catalog case
  baseline  Run 8.0.2 per-student key validation without the chatbot
  render-curl  Render a legacy metadata-checked direct FAIG request

Run `python3 -m functional_test <command> --help` for command options.
"""


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "catalog-baseline":
        from functional_test import catalog_baseline
        return catalog_baseline.main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "evaluate-catalog":
        from functional_test import catalog_evaluate
        return catalog_evaluate.main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "baseline":
        from functional_test import baseline
        return baseline.main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "render-curl":
        from functional_test import curl_renderer
        return curl_renderer.main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] in {"validate", "scenario-pack"}:
        print('The legacy chatbot-based command is retired in 8.0.2. Use catalog-baseline or the student Tests tab.', file=sys.stderr)
        return 2
    if len(sys.argv) == 1 or sys.argv[1] in {"commands", "help", "-h", "--help"}:
        print(USAGE)
        return 0
    print(f'Unknown functional_test command: {sys.argv[1]}', file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
