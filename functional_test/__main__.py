#!/usr/bin/env python3
"""Run supported FAIG functional validation from repository metadata."""

from __future__ import annotations

import sys

from functional_test import validation


USAGE = """usage: python3 -m functional_test [validate] [options]

With no command, validate passthrough and every installed scenario case.

commands:
  validate  Run live scenario validation through the deployed chatbot

Run `python3 -m functional_test --help` for validator options.
"""


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        sys.argv = [f"{sys.argv[0]} validate", *sys.argv[2:]]
    elif len(sys.argv) > 1 and sys.argv[1] in {"commands", "help"}:
        print(USAGE)
        return 0
    return validation.main()


if __name__ == "__main__":
    raise SystemExit(main())
