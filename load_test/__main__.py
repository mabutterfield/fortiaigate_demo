#!/usr/bin/env python3
"""Command dispatcher for local FAIG validation and workload generation."""

from __future__ import annotations

import sys

USAGE = """usage: python3 -m load_test <command> [options]

The legacy load generator depends on the removed 8.0.1 chatbot. It is disabled
until migrated and validated against 8.0.2; performance testing is a separate
post-functional-release activity. Use functional_test catalog-baseline for
individual functional checks.
"""


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print(USAGE)
        return 0
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
