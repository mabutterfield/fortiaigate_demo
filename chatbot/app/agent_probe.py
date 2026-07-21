#!/usr/bin/env python3
"""Run one chatbot MCP-agent turn from the deployed chatbot container."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import chatbot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe one chatbot MCP-agent turn.")
    parser.add_argument("--prompt", required=True, help="User prompt to send.")
    parser.add_argument("--provider", choices=["direct", "faig-static"], default="direct")
    parser.add_argument("--route", default="demo-a", help="FAIG static route name.")
    parser.add_argument("--model", default="", help="Override model/profile.")
    parser.add_argument("--mcp-path", choices=["direct", "fortiweb"], default="direct")
    parser.add_argument("--max-tool-rounds", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    return parser.parse_args()


def env_json_list(name: str) -> list[dict[str, Any]]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise RuntimeError(f"{name} must be a JSON list")
    return parsed


def route_by_name(routes: list[dict[str, Any]], route_name: str) -> dict[str, Any]:
    for route in routes:
        if str(route.get("name", "")).strip() == route_name:
            return route
    available = ", ".join(str(route.get("name", "")) for route in routes)
    raise RuntimeError(f"Unknown FAIG static route '{route_name}'. Available: {available}")


def main() -> int:
    args = parse_args()
    if args.provider == "direct":
        base_url = os.getenv("CHATBOT_DIRECT_BASE_URL", "").strip()
        api_key = os.getenv("CHATBOT_DIRECT_API_KEY", "not-used")
        model = args.model or os.getenv("CHATBOT_MODEL", "demo-a")
        extra_headers: dict[str, str] = {}
    else:
        faig_base_url = os.getenv("CHATBOT_FAIG_BASE_URL", "").strip()
        default_route = os.getenv("CHATBOT_FAIG_STATIC_ROUTE", "demo-a")
        routes = chatbot.build_faig_routes(
            default_route,
            env_json_list("CHATBOT_FAIG_STATIC_ROUTES_JSON"),
            f"/v1/{default_route}",
        )
        route = route_by_name(routes, args.route)
        base_url, model, extra_headers = chatbot.apply_faig_static_route(faig_base_url, route)
        if args.model:
            model = args.model
        api_key = os.getenv("CHATBOT_FAIG_API_KEY", "not-used")

    mcp_base_url = (
        os.getenv("CHATBOT_MCP_FORTIWEB_BASE_URL", "").strip()
        if args.mcp_path == "fortiweb"
        else os.getenv("CHATBOT_MCP_DIRECT_BASE_URL", "").strip()
    )
    if not base_url:
        raise RuntimeError(f"{args.provider} base URL is not configured")
    if not mcp_base_url:
        raise RuntimeError(f"{args.mcp_path} MCP base URL is not configured")

    messages = chatbot.build_model_messages(
        os.getenv("CHATBOT_FRONTEND_SYSTEM_PROMPT", "").strip() or None,
        [{"role": "user", "content": args.prompt}],
        os.getenv("CHATBOT_CONTEXT_MODE", "recent"),
        int(os.getenv("CHATBOT_CONTEXT_WINDOW", "8")),
        "",
    )
    reply, tool_events, tools = chatbot.agent_response(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        verify_tls=os.getenv("CHATBOT_VERIFY_TLS", "").lower() in {"1", "true", "yes", "on"},
        mcp_base_url=mcp_base_url,
        mcp_timeout_seconds=int(os.getenv("CHATBOT_MCP_TIMEOUT_SECONDS", "10")),
        mcp_verify_tls=os.getenv("CHATBOT_MCP_VERIFY_TLS", "").lower() in {"1", "true", "yes", "on"},
        max_tool_rounds=args.max_tool_rounds,
        extra_headers=extra_headers,
    )
    result = {
        "provider": args.provider,
        "route": args.route if args.provider == "faig-static" else None,
        "base_url": base_url,
        "model": model,
        "mcp_path": args.mcp_path,
        "mcp_base_url": mcp_base_url,
        "reply": reply,
        "tool_names": [
            tool.get("function", {}).get("name", "unknown")
            for tool in tools
            if isinstance(tool, dict)
        ],
        "tool_events": tool_events,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
