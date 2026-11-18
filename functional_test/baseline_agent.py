#!/usr/bin/env python3
"""Chatbot-free reference agent for 8.0.2 baseline validation.

Runs one scenario turn inside the cluster (normally in the MCP pod's
mcp-standard container, which has Python 3.12 and the MCP SDK): it sends the
prompt to FortiAIGate's OpenAI-compatible gateway with a per-student virtual
key, offers the scenario's tools from the standards MCP endpoint, executes
tool calls over MCP, and loops until the model answers or the round limit is
reached.

Input is one JSON object on stdin (so the virtual key never appears in a
process list); output is one JSON object on stdout:

  in:  faig_url, api_key, model, prompt, system_prompt?, mcp_url?, tools[],
       max_rounds, max_tokens, temperature
  out: reply, finish_reason, rounds, tool_events[{tool, arguments, result,
       is_error}], error?, http_status?
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any


def chat(faig_url: str, api_key: str, body: dict[str, Any], timeout: int = 180) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        faig_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, {"error_body": exc.read()[:600].decode(errors="replace")}


def openai_tool(tool: Any) -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": tool.name, "description": tool.description or "",
        "parameters": dict(tool.input_schema or {"type": "object", "properties": {}})}}


async def run(spec: dict[str, Any]) -> dict[str, Any]:
    import anyio

    messages: list[dict[str, Any]] = []
    if spec.get("system_prompt"):
        messages.append({"role": "system", "content": spec["system_prompt"]})
    messages.append({"role": "user", "content": spec["prompt"]})
    events: list[dict[str, Any]] = []
    wanted = list(spec.get("tools") or [])

    async def turn(client: Any, tools: list[dict[str, Any]]) -> dict[str, Any]:
        rounds = 0
        while True:
            body = {"model": spec["model"], "messages": messages,
                    "max_tokens": spec.get("max_tokens", 2048), "temperature": spec.get("temperature", 0.0)}
            if tools and rounds < spec.get("max_rounds", 3):
                body["tools"] = tools
            status, data = await anyio.to_thread.run_sync(chat, spec["faig_url"], spec["api_key"], body)
            if status != 200 or "choices" not in data:
                return {"error": "faig_http_error", "http_status": status, "detail": data, "rounds": rounds,
                        "reply": "", "tool_events": events}
            choice = data["choices"][0]
            message = choice.get("message") or {}
            calls = message.get("tool_calls") or []
            if not calls or client is None or rounds >= spec.get("max_rounds", 3):
                return {"reply": message.get("content") or "", "finish_reason": choice.get("finish_reason"),
                        "rounds": rounds, "tool_events": events, "http_status": status}
            rounds += 1
            messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
            for call in calls:
                name = call["function"]["name"]
                try:
                    arguments = json.loads(call["function"].get("arguments") or "{}")
                except ValueError:
                    arguments = {}
                if name not in wanted:
                    result, is_error, text = {"error": f"tool {name} is not offered"}, True, ""
                else:
                    outcome = await client.call_tool(name, arguments)
                    result, is_error = outcome.structured_content, bool(outcome.is_error)
                    text = outcome.content[0].text if outcome.content else json.dumps(result)
                events.append({"tool": name, "arguments": arguments, "result": result, "is_error": is_error})
                messages.append({"role": "tool", "tool_call_id": call.get("id", name),
                                 "content": text or json.dumps(result)})

    if not wanted or not spec.get("mcp_url"):
        return await turn(None, [])
    from mcp import Client

    async with Client(spec["mcp_url"]) as client:
        offered = [t for t in (await client.list_tools()).tools if t.name in wanted]
        missing = sorted(set(wanted) - {t.name for t in offered})
        if missing:
            return {"error": "mcp_tools_missing", "detail": missing, "reply": "", "tool_events": []}
        return await turn(client, [openai_tool(t) for t in offered])


def main() -> int:
    import anyio

    spec = json.loads(sys.stdin.read())
    try:
        result = anyio.run(run, spec)
    except Exception as exc:  # report, never echo the input (it holds the key)
        result = {"error": "agent_exception", "detail": f"{type(exc).__name__}: {exc}"[:600],
                  "reply": "", "tool_events": []}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
