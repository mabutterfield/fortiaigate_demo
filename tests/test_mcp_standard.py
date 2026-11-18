"""Tests for the standards-based MCP endpoint (mcp/chart/files/mcp_standard.py).

Requires the MCP Python SDK pinned in mcp/chart/files/requirements-standard.txt;
skipped when it is not installed in the test interpreter.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
FILES = REPO_ROOT / "mcp" / "chart" / "files"
HAVE_SDK = importlib.util.find_spec("mcp") is not None and importlib.util.find_spec("anyio") is not None


def load_modules():
    os.environ["MCP_DATA_PATH"] = str(FILES / "tools.json")
    os.environ["MCP_DOCUMENT_INDEX_PATH"] = str(FILES / "documents" / "documents.json")
    os.environ["MCP_DOCUMENT_ROOT"] = str(FILES / "documents")
    spec = importlib.util.spec_from_file_location("faig_mcp_standard_test", FILES / "mcp_standard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    legacy = module.load_legacy_module(str(FILES / "server.py"))
    legacy.DATA_PATH = str(FILES / "tools.json")
    return module, legacy


@unittest.skipUnless(HAVE_SDK, "MCP Python SDK not installed (see mcp/chart/files/requirements-standard.txt)")
class McpStandardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.std, cls.legacy = load_modules()

    def run_client(self, coroutine_factory, allowed_origins=None):
        import anyio
        from mcp import Client

        server, _ = self.std.build_server(self.legacy)

        async def runner():
            async with Client(server) as client:
                return await coroutine_factory(client)

        return anyio.run(runner)

    def test_every_legacy_tool_is_converted(self):
        names = [d["function"]["name"] for d in self.legacy.TOOLS]
        converted = [self.std.convert_tool(d) for d in self.legacy.TOOLS]
        self.assertEqual([t.name for t in converted], names)
        for tool in converted:
            self.assertEqual(tool.input_schema.get("type"), "object")
            self.assertTrue(tool.annotations.read_only_hint)
            self.assertFalse(tool.annotations.destructive_hint)
        fortigate = [t for t in converted if t.name.startswith("fortigate_")]
        self.assertTrue(fortigate and all(t.annotations.open_world_hint for t in fortigate))

    def test_tools_list_over_protocol(self):
        tools = self.run_client(lambda c: c.list_tools()).tools
        self.assertEqual(len(tools), len(self.legacy.TOOLS))
        self.assertIn("employee_sensitive_lookup", {t.name for t in tools})

    def test_call_matches_legacy_result(self):
        arguments = {"employee_id": "EMP-5001"}
        result = self.run_client(lambda c: c.call_tool("employee_sensitive_lookup", arguments))
        ok, expected = self.legacy.run_tool("employee_sensitive_lookup", dict(arguments))
        self.assertTrue(ok)
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content, expected)
        self.assertEqual(json.loads(result.content[0].text), expected)
        self.assertNotIn("credit_card_number", json.dumps(result.structured_content))

    def test_invalid_arguments_are_tool_errors(self):
        result = self.run_client(lambda c: c.call_tool("employee_lookup", {"unexpected": 1}))
        self.assertTrue(result.is_error)
        self.assertEqual(result.structured_content["error"], "invalid arguments")

    def test_tool_failure_is_tool_error(self):
        result = self.run_client(lambda c: c.call_tool("employee_lookup", {"employee_id": "EMP-0000"}))
        self.assertTrue(result.is_error)

    def test_unknown_tool_is_protocol_error(self):
        from mcp.shared.exceptions import MCPError

        async def call_unknown(client):
            with self.assertRaises(MCPError) as raised:
                await client.call_tool("no_such_tool", {})
            return raised.exception

        self.assertIn("Unknown tool", str(self.run_client(call_unknown)))

    def test_policy_hook_can_hide_and_deny_tools(self):
        import anyio
        from mcp import Client
        from mcp.shared.exceptions import MCPError

        class OnlyEcho(self.std.ToolPolicy):
            def visible(self, tools, meta):
                return [t for t in tools if t.name == "echo"]

            def may_call(self, name, meta):
                return name == "echo"

        server, _ = self.std.build_server(self.legacy, OnlyEcho())

        async def runner():
            async with Client(server) as client:
                names = [t.name for t in (await client.list_tools()).tools]
                with self.assertRaises(MCPError):
                    await client.call_tool("employee_lookup", {"employee_id": "EMP-5001"})
                return names

        self.assertEqual(anyio.run(runner), ["echo"])

    def test_origin_guard(self):
        import anyio

        sent = []

        async def inner(scope, receive, send):
            sent.append("inner")

        async def call(headers):
            messages = []

            async def send(message):
                messages.append(message)

            async def receive():
                return {"type": "http.request", "body": b""}

            guard = self.std.OriginGuard(inner, ["https://chat.lab"])
            await guard({"type": "http", "headers": headers, "method": "GET", "path": "/mcp"}, receive, send)
            return messages

        blocked = anyio.run(call, [(b"origin", b"https://evil.example")])
        self.assertEqual(blocked[0]["status"], 403)
        anyio.run(call, [(b"origin", b"https://chat.lab")])
        anyio.run(call, [])
        self.assertEqual(sent, ["inner", "inner"])


if __name__ == "__main__":
    unittest.main()
