#!/usr/bin/env python3
"""Run supported FAIG functional validation from repository metadata."""

from __future__ import annotations

import sys

from functional_test import curl_renderer, validation


USAGE = """usage: python3 -m functional_test <command> [options]

With no command, validation runs as a transition convenience.

commands:
  validate  Run live scenario validation through the deployed chatbot
  render-curl  Render one metadata-checked direct FAIG request

Run `python3 -m functional_test <command> --help` for command options.
"""


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "render-curl":
        return curl_renderer.main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        sys.argv = [f"{sys.argv[0]} validate", *sys.argv[2:]]
    elif len(sys.argv) > 1 and sys.argv[1] in {"commands", "help", "-h", "--help"}:
        print(USAGE)
        return 0
    return validation.main()


if __name__ == "__main__":
    raise SystemExit(main())
