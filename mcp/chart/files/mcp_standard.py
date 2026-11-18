"""Standards-based MCP endpoint for the demo tools.

Serves the Model Context Protocol (JSON-RPC 2.0 over Streamable HTTP) with the
official MCP Python SDK, in parallel with the legacy custom HTTP facade in
server.py. The tool definitions and implementations are imported from
server.py unchanged, so both endpoints expose identical tools and results.

Trusted single-operator lab endpoint: no client authentication or per-client
authorization. Tool visibility and invocation go through ToolPolicy so those
controls can be added later. Browser requests are limited by an Origin
allow-list; server-side clients (no Origin header) are accepted.
"""
import importlib.util
import json
import logging
import os
from pathlib import Path

import anyio
import jsonschema
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.shared.exceptions import MCPError
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

LEGACY_SERVER_PATH = os.environ.get("MCP_LEGACY_SERVER_PATH",
                                    str(Path(__file__).resolve().with_name("server.py")))
LISTEN_HOST = os.environ.get("MCP_STANDARD_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("MCP_STANDARD_PORT", "8001"))
MCP_PATH = os.environ.get("MCP_STANDARD_PATH", "/mcp")
STATELESS = os.environ.get("MCP_STANDARD_STATELESS", "false").strip().lower() in {"1", "true", "yes", "on"}
JSON_RESPONSE = os.environ.get("MCP_STANDARD_JSON_RESPONSE", "false").strip().lower() in {"1", "true", "yes", "on"}
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("MCP_STANDARD_ALLOWED_ORIGINS", "").split(",") if o.strip()]
SERVER_NAME = "faig-demo-tools"
SERVER_VERSION = "1.0.0"
OPEN_WORLD_PREFIXES = ("fortigate_",)

logger = logging.getLogger("mcp_standard")


def load_legacy_module(path=LEGACY_SERVER_PATH):
    """Import server.py for its TOOLS registry and run_tool implementation."""
    spec = importlib.util.spec_from_file_location("faig_mcp_legacy_tools", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load tool registry from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def convert_tool(definition):
    """Convert an OpenAI-style function definition into MCP tool metadata."""
    function = definition["function"]
    name = function["name"]
    schema = dict(function.get("parameters") or {"type": "object", "properties": {}})
    schema.setdefault("type", "object")
    open_world = name.startswith(OPEN_WORLD_PREFIXES)
    return types.Tool(
        name=name,
        title=name.replace("_", " ").title(),
        description=function.get("description", ""),
        input_schema=schema,
        annotations=types.ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=not open_world,
            open_world_hint=open_world,
        ),
    )


class ToolPolicy:
    """Server-side tool policy hook. The trusted demo client may see and call every tool.

    Future per-client scoping replaces these methods; callers must not assume
    every client can list or invoke every tool.
    """

    def visible(self, tools, request_meta):
        return list(tools)

    def may_call(self, tool_name, request_meta):
        return True


def request_meta(ctx):
    """Non-secret request metadata for policy decisions (never logged with credentials)."""
    request = getattr(ctx, "request", None)
    headers = getattr(request, "headers", None) or {}
    return {"user_agent": headers.get("user-agent", ""), "client": getattr(getattr(request, "client", None), "host", None)}


def tool_result(ok, result):
    """Text content for any client plus structured content; tool failures are MCP tool errors."""
    text = json.dumps(result, indent=2, sort_keys=True)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structured_content=result if isinstance(result, dict) else {"result": result},
        is_error=not ok,
    )


def build_server(legacy=None, policy=None):
    legacy = legacy or load_legacy_module()
    policy = policy or ToolPolicy()
    tools = {t.name: t for t in (convert_tool(d) for d in legacy.TOOLS)}

    async def on_list_tools(ctx, params):
        return types.ListToolsResult(tools=policy.visible(tools.values(), request_meta(ctx)))

    async def on_call_tool(ctx, params):
        name = params.name
        meta = request_meta(ctx)
        if name not in tools or not policy.may_call(name, meta):
            raise MCPError(code=types.INVALID_PARAMS, message=f"Unknown tool: {name}")
        arguments = dict(params.arguments or {})
        try:
            jsonschema.validate(arguments, tools[name].input_schema)
        except jsonschema.ValidationError as exc:
            # Input validation failures are tool errors so the model can correct itself.
            return tool_result(False, {"error": "invalid arguments", "detail": exc.message, "tool": name})
        ok, result = await anyio.to_thread.run_sync(legacy.run_tool, name, arguments)
        logger.info("tools/call %s ok=%s", name, ok)
        return tool_result(ok, result)

    return Server(
        SERVER_NAME,
        version=SERVER_VERSION,
        title="FortiAIGate demo tools",
        instructions="Deterministic synthetic demo tools for FortiAIGate scenarios. All data is synthetic.",
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    ), tools


class OriginGuard:
    """Reject browser requests whose Origin is not explicitly allowed."""

    def __init__(self, app, allowed_origins):
        self.app = app
        self.allowed = set(allowed_origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            origin = dict(scope.get("headers") or []).get(b"origin")
            if origin is not None and origin.decode("latin-1") not in self.allowed:
                response = PlainTextResponse("Origin not allowed", status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def build_app(legacy=None, policy=None, allowed_origins=None):
    server, tools = build_server(legacy, policy)

    async def health(request: Request):
        return JSONResponse({"status": "ok", "protocol": "mcp-streamable-http", "path": MCP_PATH,
                             "tools": len(tools)})

    app = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=STATELESS,
        json_response=JSON_RESPONSE,
        host=LISTEN_HOST,
        custom_starlette_routes=[Route("/health", health, methods=["GET"])],
    )
    return OriginGuard(app, ALLOWED_ORIGINS if allowed_origins is None else allowed_origins)


async def check_endpoint(url):
    """Act as a standards MCP client: initialize, list tools and call a safe tool."""
    from mcp import Client

    async with Client(url) as client:
        tools = (await client.list_tools()).tools
        print(f"tools/list: {len(tools)} tools")
        result = await client.call_tool("employee_lookup", {"employee_id": "EMP-5001"})
        print(f"tools/call employee_lookup: is_error={result.is_error} "
              f"keys={sorted((result.structured_content or {}).keys())}")
        invalid = await client.call_tool("employee_lookup", {})
        print(f"tools/call invalid arguments: is_error={invalid.is_error}")
        return bool(tools) and not result.is_error and invalid.is_error


def main():
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        ok = anyio.run(check_endpoint, sys.argv[2])
        print("PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)

    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Standards MCP endpoint on %s:%s%s (stateless=%s)", LISTEN_HOST, LISTEN_PORT, MCP_PATH, STATELESS)
    uvicorn.run(build_app(), host=LISTEN_HOST, port=LISTEN_PORT, log_level="info")


if __name__ == "__main__":
    main()
