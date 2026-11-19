"""Tests for the catalog-driven chatbot helpers (chatbot/lab-chatbot/chart/files/lab_catalog_chat.py)."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lab_catalog_chat",
                                              REPO_ROOT / "chatbot/lab-chatbot/chart/files/lab_catalog_chat.py")
lc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lc)

from catalog802.loader import build_views, load  # noqa: E402
from catalog802.result_contract import evaluate  # noqa: E402
from functional_test.result_contract import contains_sensitive  # noqa: E402

KID = "1b65f1df-d00f-45d4-abba-7ade33eeb8be"


def student_view():
    catalog, errors = load(REPO_ROOT)
    assert not errors, errors
    return build_views(catalog)["student"]


class Logs:
    """Fake gateway Traffic Log API: rows for a key, details by uuid (prompt carries the marker)."""

    def __init__(self, verdicts, key="student03_hr-tool-dlp_redact", status=200):
        self.verdicts, self.key, self.status, self.prompt = verdicts, key, status, ""

    def __call__(self, **query):
        if self.status != 200:
            return self.status, {"error": "no FAIG session"}
        if query.get("uuid"):
            index = int(query["uuid"][1:])
            return 200, {"uuid": query["uuid"], "keyAlias": self.key, "verdictLabel": self.verdicts[index],
                         "prompt": {"original": self.prompt}, "toolDefinitions": ["big"]}
        return 200, {"items": [{"uuid": f"u{i}", "keyAlias": self.key, "timeStamp": 10**13}
                               for i in range(len(self.verdicts))]}


class CatalogViewTests(unittest.TestCase):
    def setUp(self):
        view = student_view()
        self.scenarios = {i["id"]: i for i in view["items"]}
        self.platform = view["platform"]

    def test_load_view_reports_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("not found", lc.load_view(tmp + "/catalog-student.json")[2])
            Path(tmp, "catalog-student.json").write_text(json.dumps(student_view()))
            scenarios, platform, error = lc.load_view(tmp + "/catalog-student.json")
        self.assertIsNone(error)
        self.assertEqual(set(scenarios), {"fortistore-injection", "hr-tool-dlp", "resume-tool-injection"})
        self.assertIn("hello_world", platform)

    def test_plan_selects_compromised_frontend_only_when_the_test_asks(self):
        fortistore = self.scenarios["fortistore-injection"]
        normal = next(t for t in fortistore["tests"] if t["id"] == "block-attack")
        compromised = next(t for t in fortistore["tests"] if t["id"] == "block-compromised")
        self.assertEqual(lc.plan_test(fortistore, normal)["system_prompt"], "")
        self.assertTrue(lc.plan_test(fortistore, compromised)["system_prompt"].startswith("# FortiStore"))
        self.assertEqual(lc.plan_test(fortistore, normal)["model"], "fortistore-injection")

    def test_plan_adds_extended_tools_only_when_required(self):
        resume = self.scenarios["resume-tool-injection"]
        for test in resume["tests"]:
            plan = lc.plan_test(resume, test)
            needed = set(test["required_tools"]) | set(test["attack_tools"])
            self.assertTrue(needed <= set(plan["tools"]), test["id"])

    def test_mapped_key_needs_value_and_newest_wins(self):
        records = [{"scenario_id": "hr-tool-dlp", "action": "alert", "secret": "", "updated_at": 9},
                   {"scenario_id": "hr-tool-dlp", "action": "alert", "secret": "a", "updated_at": 1, "key_name": "old"},
                   {"scenario_id": "hr-tool-dlp", "action": "alert", "secret": "b", "updated_at": 2, "key_name": "new"},
                   {"scenario_id": "hr-tool-dlp", "action": "alert", "secret": "c", "updated_at": 3, "status": "missing"}]
        self.assertEqual(lc.mapped_key(records, "hr-tool-dlp", "alert")["key_name"], "new")
        self.assertIsNone(lc.mapped_key(records, "hr-tool-dlp", "block"))
        self.assertNotIn("secret", json.dumps(lc.public_rows(records)))


class RunCaseTests(unittest.TestCase):
    def setUp(self):
        view = student_view()
        self.hr = next(i for i in view["items"] if i["id"] == "hr-tool-dlp")
        self.platform = view["platform"]
        self.redact = next(t for t in self.hr["tests"] if t["action"] == "redact")
        self.key = {"key_name": "student03_hr-tool-dlp_redact", "secret": "faig_x", "faig_key_id": KID}

    def run_case(self, reply, logs, tools=("employee_sensitive_lookup",), rounds=1, error=None, test=None, plan=None):
        seen = {}

        def agent(spec):
            seen.update(spec)
            logs.prompt = spec["prompt"]
            events = [{"tool": t, "result": {"ssn": "489-36-8350"}} for t in tools]
            return {"reply": reply, "tool_events": events, "rounds": rounds, "error": error, "http_status": 401 if error else 200}
        test = test or self.redact
        result = lc.run_case(agent=agent, fetch_logs=logs, evaluate=evaluate, contains_sensitive=contains_sensitive,
                             test=test, plan=plan or lc.plan_test(self.hr, test), key=self.key, faig_url="http://faig",
                             mcp_url="http://mcp", scenario_version=self.hr["scenario_version"],
                             sleep=lambda _: None, clock=lambda: 1000.0, log_wait=0)
        return result, seen

    def test_redact_pass_with_marker_matched_rows(self):
        result, spec = self.run_case("SSN: [REDACTED_SSN_1]", Logs(["log", "redact"]))
        self.assertEqual((result["outcome"], result["verdict"]), ("pass", "redact"), result["reasons"])
        self.assertTrue(lc.MARKER.search(spec["prompt"]))
        self.assertTrue(spec["record_exchanges"])
        self.assertNotIn("toolDefinitions", json.dumps(result["log_entries"]))
        self.assertNotIn("faig_x", json.dumps({k: v for k, v in result.items() if k != "exchanges"}))

    def test_unredacted_reply_fails(self):
        result, _ = self.run_case("SSN: 489-36-8350", Logs(["log", "redact"]))
        self.assertEqual(result["outcome"], "fail")

    def test_missing_logs_are_incomplete_not_pass(self):
        result, _ = self.run_case("SSN: [REDACTED_SSN_1]", Logs([], status=403))
        self.assertEqual((result["outcome"], result["verdict"]), ("incomplete", "unknown"))
        self.assertTrue(result["log_error"])

    def test_rows_without_marker_are_ignored(self):
        logs = Logs(["redact", "redact"])
        result, _ = self.run_case("SSN: [REDACTED_SSN_1]", logs)
        logs.prompt = "unrelated"   # a later run on the same key without this marker
        rows, _, _ = lc.match_rows(logs, self.key["key_name"], 0, "[faig-test-" + "0" * 32 + "]")
        self.assertEqual(rows, [])

    def test_hello_world_and_key_status(self):
        hello = lc.hello_world_test(self.platform)
        plan = {"prompt": "Reply with exactly: Hello.", "system_prompt": "", "tools": [], "max_rounds": 0,
                "model": "hr-tool-dlp"}
        result, _ = self.run_case("Hello.", Logs(["log"]), tools=(), rounds=0, test=hello, plan=plan)
        self.assertEqual(result["outcome"], "pass")
        self.assertEqual(lc.key_status_for(result), "ok")
        bad, _ = self.run_case("", Logs([]), tools=(), rounds=0, error="http_error", test=hello, plan=plan)
        self.assertEqual(lc.key_status_for(bad), "invalid")


if __name__ == "__main__":
    unittest.main()
