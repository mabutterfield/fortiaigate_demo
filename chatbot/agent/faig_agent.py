"""Shared agent loop for FortiAIGate 8.0.2 lab clients.

One turn: send the conversation to an OpenAI-compatible endpoint (FortiAIGate
`/ai/openai/v1` with a per-student virtual key, or LiteLLM directly with the
shared virtual key), offer the scenario's tools from the standards MCP
endpoint, execute tool calls over MCP, and loop until the model answers or the
round limit is reached.

Used by the chatbot-free baseline (`functional_test/baseline_agent.py`) and the
8.0.2 student chatbot, so both exercise the same logic. Dependencies: Python
standard library plus `anyio` and the MCP Python SDK (only when tools are
offered). Keys are never recorded in results or exchanges.

spec fields:
  base_url       OpenAI-compatible base URL ending in /v1 (alias: faig_url)
  api_key        bearer key for that endpoint
  model          model alias
  prompt         user message for this turn
  system_prompt  optional frontend/system instructions
  history        optional prior messages (user/assistant/tool) to continue
  mcp_url        standards MCP endpoint (required when tools are offered)
  tools          tool names to offer (empty: no MCP)
  max_rounds     tool-call round limit (default 3)
  max_tokens, temperature
  record_exchanges  include each request body and response (default false)

result fields:
  reply, finish_reason, rounds, http_status, tool_events[], messages[],
  exchanges[] (when recorded), error and detail (on failure)
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Awaitable, Callable

ChatFn = Callable[[str, str, dict[str, Any]], tuple[int, dict[str, Any]]]


def chat_completion(base_url: str, api_key: str, body: dict[str, Any], timeout: int = 180) -> tuple[int, dict[str, Any]]:
    """POST one chat completion; returns (HTTP status, JSON body or error excerpt)."""
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, {"error_body": exc.read()[:2000].decode(errors="replace")}


def openai_tool(tool: Any) -> dict[str, Any]:
    """Convert MCP tool metadata into an OpenAI function tool definition."""
    return {"type": "function", "function": {
        "name": tool.name, "description": tool.description or "",
        "parameters": dict(tool.input_schema or {"type": "object", "properties": {}})}}


def initial_messages(spec: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if spec.get("system_prompt"):
        messages.append({"role": "system", "content": spec["system_prompt"]})
    messages.extend(spec.get("history") or [])
    messages.append({"role": "user", "content": spec["prompt"]})
    return messages


async def _loop(spec: dict[str, Any], session: Any, tools: list[dict[str, Any]], chat: ChatFn) -> dict[str, Any]:
    import anyio

    base_url = spec.get("base_url") or spec["faig_url"]
    max_rounds = int(spec.get("max_rounds", 3))
    wanted = set(spec.get("tools") or [])
    record = bool(spec.get("record_exchanges"))
    messages = initial_messages(spec)
    events: list[dict[str, Any]] = []
    exchanges: list[dict[str, Any]] = []
    rounds = 0

    def finish(**fields: Any) -> dict[str, Any]:
        result = {"rounds": rounds, "tool_events": events, "messages": messages, **fields}
        if record:
            result["exchanges"] = exchanges
        return result

    while True:
        body: dict[str, Any] = {"model": spec["model"], "messages": list(messages),
                                "max_tokens": spec.get("max_tokens", 2048), "temperature": spec.get("temperature", 0.0)}
        if tools and rounds < max_rounds:
            body["tools"] = tools
        status, data = await anyio.to_thread.run_sync(chat, base_url, spec["api_key"], body)
        if record:
            exchanges.append({"round": rounds, "request": body, "status": status, "response": data})
        if status != 200 or "choices" not in data:
            return finish(error="http_error", http_status=status, detail=data, reply="")
        choice = data["choices"][0]
        message = choice.get("message") or {}
        calls = message.get("tool_calls") or []
        if not calls or session is None or rounds >= max_rounds:
            messages.append({"role": "assistant", "content": message.get("content") or ""})
            return finish(reply=message.get("content") or "", finish_reason=choice.get("finish_reason"),
                          http_status=status)
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
                outcome = await session.call_tool(name, arguments)
                result, is_error = outcome.structured_content, bool(outcome.is_error)
                text = outcome.content[0].text if outcome.content else ""
            events.append({"tool": name, "arguments": arguments, "result": result, "is_error": is_error})
            messages.append({"role": "tool", "tool_call_id": call.get("id", name),
                             "content": text or json.dumps(result)})


async def run_turn(spec: dict[str, Any], *, chat: ChatFn = chat_completion, session: Any = None) -> dict[str, Any]:
    """Run one agent turn. `session` may be any object with async list_tools()/call_tool()."""
    wanted = list(spec.get("tools") or [])
    if not wanted:
        return await _loop(spec, None, [], chat)

    async def with_session(active: Any) -> dict[str, Any]:
        offered = [t for t in (await active.list_tools()).tools if t.name in wanted]
        missing = sorted(set(wanted) - {t.name for t in offered})
        if missing:
            return {"error": "mcp_tools_missing", "detail": missing, "reply": "", "tool_events": [],
                    "messages": [], "rounds": 0}
        return await _loop(spec, active, [openai_tool(t) for t in offered], chat)

    if session is not None:
        return await with_session(session)
    if not spec.get("mcp_url"):
        return {"error": "mcp_url_missing", "detail": "tools requested without mcp_url", "reply": "",
                "tool_events": [], "messages": [], "rounds": 0}
    from mcp import Client

    async with Client(spec["mcp_url"]) as client:
        return await with_session(client)


def run_turn_sync(spec: dict[str, Any], **kwargs: Awaitable[Any]) -> dict[str, Any]:
    """Blocking wrapper for synchronous callers such as Streamlit."""
    import anyio

    return anyio.run(lambda: run_turn(spec, **kwargs))
