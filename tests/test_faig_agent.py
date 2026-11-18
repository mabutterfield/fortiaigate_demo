"""Unit tests for the shared agent loop (chatbot/agent/faig_agent.py)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
HAVE_ANYIO = importlib.util.find_spec("anyio") is not None
SECRET = "faig_unit_test_secret"


def load_agent():
    spec = importlib.util.spec_from_file_location("faig_agent_test", REPO_ROOT / "chatbot" / "agent" / "faig_agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tool_call(name, arguments, call_id="call-1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


class FakeChat:
    """Returns scripted chat completion responses and records request bodies."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.bodies, self.keys = [], []

    def __call__(self, base_url, api_key, body):
        self.bodies.append(json.loads(json.dumps(body)))
        self.keys.append(api_key)
        return self.responses.pop(0)


def ok(content="", calls=None, finish="stop"):
    message = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    return 200, {"choices": [{"message": message, "finish_reason": finish}]}


class FakeSession:
    def __init__(self, names):
        self.names, self.calls = names, []

    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name=n, description=n, input_schema={"type": "object"})
                                      for n in self.names])

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        result = {"tool": name, "echo": arguments}
        return SimpleNamespace(structured_content=result, is_error=False,
                               content=[SimpleNamespace(text=json.dumps(result))])


@unittest.skipUnless(HAVE_ANYIO, "anyio not installed")
class FaigAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = load_agent()

    def run_turn(self, spec, chat, session=None):
        import anyio

        base = {"base_url": "http://faig/ai/openai/v1", "api_key": SECRET, "model": "hr-tool-dlp",
                "prompt": "Get sensitive information for EMP-5001.", "max_rounds": 3}
        return anyio.run(lambda: self.agent.run_turn({**base, **spec}, chat=chat, session=session))

    def test_plain_turn_without_tools(self):
        chat = FakeChat(ok("hello"))
        result = self.run_turn({"system_prompt": "be brief", "history": [{"role": "user", "content": "hi"},
                                                                          {"role": "assistant", "content": "hey"}]}, chat)
        self.assertEqual((result["reply"], result["rounds"], result["http_status"]), ("hello", 0, 200))
        self.assertEqual([m["role"] for m in chat.bodies[0]["messages"]], ["system", "user", "assistant", "user"])
        self.assertNotIn("tools", chat.bodies[0])
        self.assertEqual(result["messages"][-1], {"role": "assistant", "content": "hello"})

    def test_tool_loop_calls_mcp_and_feeds_results_back(self):
        session = FakeSession(["employee_lookup", "employee_sensitive_lookup"])
        chat = FakeChat(ok(calls=[tool_call("employee_sensitive_lookup", {"employee_id": "EMP-5001"})], finish="tool_calls"),
                        ok("done"))
        result = self.run_turn({"tools": ["employee_sensitive_lookup"]}, chat, session)
        self.assertEqual(result["reply"], "done")
        self.assertEqual(result["rounds"], 1)
        self.assertEqual(session.calls, [("employee_sensitive_lookup", {"employee_id": "EMP-5001"})])
        self.assertEqual([t["function"]["name"] for t in chat.bodies[0]["tools"]], ["employee_sensitive_lookup"])
        self.assertEqual(chat.bodies[1]["messages"][-1]["role"], "tool")
        self.assertEqual(result["tool_events"][0]["result"]["echo"], {"employee_id": "EMP-5001"})

    def test_tool_not_offered_is_refused(self):
        session = FakeSession(["employee_lookup", "cloud_bucket_list_demo"])
        chat = FakeChat(ok(calls=[tool_call("cloud_bucket_list_demo", {})]), ok("ok"))
        result = self.run_turn({"tools": ["employee_lookup"]}, chat, session)
        self.assertEqual(session.calls, [])
        self.assertTrue(result["tool_events"][0]["is_error"])

    def test_round_limit_stops_tool_offers(self):
        session = FakeSession(["employee_lookup"])
        chat = FakeChat(ok(calls=[tool_call("employee_lookup", {})]), ok("final"))
        result = self.run_turn({"tools": ["employee_lookup"], "max_rounds": 1}, chat, session)
        self.assertEqual((result["rounds"], result["reply"]), (1, "final"))
        self.assertNotIn("tools", chat.bodies[1])

    def test_missing_mcp_tool_is_reported(self):
        result = self.run_turn({"tools": ["employee_lookup"]}, FakeChat(), FakeSession([]))
        self.assertEqual((result["error"], result["detail"]), ("mcp_tools_missing", ["employee_lookup"]))

    def test_exchanges_record_payloads_but_never_the_key(self):
        chat = FakeChat(ok("hi"))
        result = self.run_turn({"record_exchanges": True}, chat)
        self.assertEqual(len(result["exchanges"]), 1)
        self.assertEqual(result["exchanges"][0]["request"]["model"], "hr-tool-dlp")
        self.assertEqual(chat.keys, [SECRET])
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn("exchanges", self.run_turn({}, FakeChat(ok("hi"))))

    def test_http_error_is_returned(self):
        result = self.run_turn({"record_exchanges": True}, FakeChat((401, {"error_body": "bad key"})))
        self.assertEqual((result["error"], result["http_status"]), ("http_error", 401))
        self.assertEqual(result["exchanges"][0]["status"], 401)

    def test_legacy_faig_url_field_still_works(self):
        chat = FakeChat(ok("hi"))
        import anyio

        spec = {"faig_url": "http://faig/ai/openai/v1", "api_key": SECRET, "model": "m", "prompt": "p"}
        self.assertEqual(anyio.run(lambda: self.agent.run_turn(spec, chat=chat))["reply"], "hi")


if __name__ == "__main__":
    unittest.main()
