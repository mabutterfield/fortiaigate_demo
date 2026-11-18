#!/usr/bin/env python3
"""In-cluster runner for the chatbot-free 8.0.2 baseline.

Reads one agent spec as JSON on stdin (so the virtual key never appears in a
process list), runs one turn with the shared agent loop in
chatbot/agent/faig_agent.py (staged next to this file), and prints one JSON
result. See faig_agent.py for the spec and result fields. Runs in the MCP
pod's mcp-standard container, which has Python 3.12 and the MCP SDK.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    try:
        import faig_agent

        result = faig_agent.run_turn_sync(json.loads(sys.stdin.read()))
    except Exception as exc:  # report, never echo the input (it holds the key)
        result = {"error": "agent_exception", "detail": f"{type(exc).__name__}: {exc}"[:600],
                  "reply": "", "tool_events": []}
    result.pop("messages", None)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
