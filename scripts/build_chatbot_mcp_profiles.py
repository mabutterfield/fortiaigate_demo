#!/usr/bin/env python3
"""Build chatbot MCP tool profiles from installed scenario slot metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import instruction_profiles
except ModuleNotFoundError:
    from scripts import instruction_profiles


def ordered_unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def label_from_metadata(metadata: dict[str, Any], profile_name: str) -> str:
    display_name = str(metadata.get("display_name") or "").strip()
    if display_name:
        return display_name
    return profile_name.replace("-", " ").title()


def mcp_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    mcp = metadata.get("mcp")
    if isinstance(mcp, dict):
        return mcp
    return {
        "enabled": bool(metadata.get("tool_profile") or metadata.get("required_tools")),
        "tool_profile": metadata.get("tool_profile", ""),
        "required_tools": metadata.get("required_tools", []),
    }


def build_profiles(slots: list[str], *, include_debug_all_server_tools: bool) -> dict[str, Any]:
    profiles_by_name: dict[str, dict[str, Any]] = {}
    all_tools: list[str] = []
    installed_slots: list[dict[str, Any]] = []

    for slot in slots:
        metadata = instruction_profiles.slot_metadata(slot)
        slot_name = instruction_profiles.resolve_slot(slot)
        mcp = mcp_from_metadata(metadata)
        tool_profile = str(mcp.get("tool_profile") or "").strip()
        required_tools = [
            str(tool).strip()
            for tool in mcp.get("required_tools", [])
            if str(tool).strip()
        ]
        mcp_enabled = bool(mcp.get("enabled", True))
        installed_slots.append(
            {
                "slot": slot_name,
                "scenario_id": metadata.get("scenario_id", ""),
                "tool_profile": tool_profile,
                "required_tools": required_tools,
                "mcp_enabled": mcp_enabled,
            }
        )
        if not mcp_enabled or not tool_profile or not required_tools:
            continue

        all_tools.extend(required_tools)
        existing = profiles_by_name.get(tool_profile)
        if existing:
            existing["tools"] = ordered_unique(existing["tools"] + required_tools)
            continue
        profiles_by_name[tool_profile] = {
            "name": tool_profile,
            "label": str(mcp.get("label") or label_from_metadata(metadata, tool_profile)).strip(),
            "tools": ordered_unique(required_tools),
        }

    profiles = []
    all_tools = ordered_unique(all_tools)
    if all_tools:
        profiles.append(
            {
                "name": "all-tools",
                "label": "All installed tools",
                "tools": all_tools,
            }
        )
    else:
        profiles.append(
            {
                "name": "all-tools",
                "label": "All installed tools (none)",
                "tools": [],
            }
        )

    profiles.extend(profiles_by_name[name] for name in sorted(profiles_by_name))

    if include_debug_all_server_tools:
        profiles.append(
            {
                "name": "debug-all-server-tools",
                "label": "Debug - all MCP server tools",
                "tools": [],
                "allow_all": True,
            }
        )

    return {
        "default_profile": "all-tools",
        "profiles": profiles,
        "installed_slots": installed_slots,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build chatbot MCP tool profiles from installed scenario metadata."
    )
    parser.add_argument(
        "--slots",
        nargs="+",
        default=["demo-a", "demo-b"],
        help="Instruction slots to inspect for installed scenario MCP metadata.",
    )
    parser.add_argument(
        "--include-debug-all-server-tools",
        action="store_true",
        help="Add a troubleshooting profile that exposes every tool returned by the MCP server.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(build_profiles(args.slots, include_debug_all_server_tools=args.include_debug_all_server_tools), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
