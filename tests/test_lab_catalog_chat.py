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

    def run_case(self, reply, logs, tools=("employee_sensitive_lookup",), rounds=1, error=None, test=None, plan=None,
                 grade=None):
        seen = {}

        def agent(spec):
            seen.update(spec)
            logs.prompt = spec["prompt"]
            events = [{"tool": t, "result": {"ssn": "489-36-8350"}} for t in tools]
            return {"reply": reply, "tool_events": events, "rounds": rounds, "error": error, "http_status": 401 if error else 200}
        test = test or self.redact
        result = lc.run_case(agent=agent, fetch_logs=logs, evaluate=grade or evaluate, contains_sensitive=contains_sensitive,
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

    def test_http_failures_are_named(self):
        """Change 2026-11-20: a rejected key reads as such, not as an unknown verdict."""
        hello = lc.hello_world_test(self.platform)
        plan = {"prompt": "Reply with exactly: Hello.", "system_prompt": "", "tools": [], "max_rounds": 0,
                "model": "hr-tool-dlp"}
        bad, _ = self.run_case("", Logs([]), tools=(), rounds=0, error="http_error", test=hello, plan=plan)
        self.assertEqual(bad["outcome"], "incomplete")
        self.assertIn("rejected the key (HTTP 401", lc.http_failure(bad))
        body = '{"error":{"message":"invalid or unknown API key","type":"authentication_error"}}'
        raw = {"error": "http_error", "http_status": 401, "detail": {"error_body": body}}
        self.assertIn("HTTP 401: invalid or unknown API key", lc.http_failure(raw))
        self.assertIn("refused the request (HTTP 400", lc.http_failure(dict(raw, http_status=400)))
        self.assertIn("limit", lc.http_failure(dict(raw, http_status=429)))
        self.assertIn("failed (HTTP 502", lc.http_failure(dict(raw, http_status=502, detail={"error_body": "<html>"})))
        self.assertEqual(lc.http_failure({"error": "", "reply": "ok"}), "")

    def test_gui_only_hello_world_is_ungraded_but_key_ok(self):
        """Change 2026-11-20: no inspection, so no Traffic Log rows; a reply still proves the key."""
        hello = lc.hello_world_test(self.platform)
        plan = {"prompt": "Reply with exactly: Hello.", "system_prompt": "", "tools": [], "max_rounds": 0,
                "model": "hr-tool-dlp"}
        result, _ = self.run_case("Hello.", Logs([]), tools=(), rounds=0, test=hello, plan=plan,
                                  grade=lc.observe)
        self.assertEqual((result["outcome"], result["verdict"]), ("observed", "unknown"))
        self.assertEqual(lc.key_status_for(result), "ok")
        empty, _ = self.run_case("", Logs([]), tools=(), rounds=0, test=hello, plan=plan, grade=lc.observe)
        self.assertEqual(lc.key_status_for(empty), "error")


class ProbeTests(unittest.TestCase):
    """Ungraded 'Try a prompt' probe (Change 2026-11-19)."""

    def setUp(self):
        self.scenarios = {i["id"]: i for i in student_view()["items"]}
        self.store = self.scenarios["fortistore-injection"]

    def test_prompt_choices_cover_every_catalog_prompt_attack_first(self):
        choices = lc.prompt_choices(self.store)
        total = sum(len(g) for g in self.store["prompts"].values())
        self.assertEqual(len(choices), total)
        self.assertEqual(choices[0]["group"], "attack")

    def test_related_tests_follow_prompt_action_and_frontend_mode(self):
        self.assertEqual([t["id"] for t in lc.related_tests(self.store, "block", "attack-01", False)], ["block-attack"])
        self.assertEqual([t["id"] for t in lc.related_tests(self.store, "block", "attack-01", True)],
                         ["block-compromised"])
        self.assertEqual(lc.related_tests(self.store, "block", "clean-01", False), [])
        self.assertEqual(lc.related_tests(self.store, "block", None, False), [])

    def test_probe_plan_matches_the_related_test_plan(self):
        test = next(t for t in self.store["tests"] if t["id"] == "block-compromised")
        expected = lc.plan_test(self.store, test)
        stub, plan = lc.probe_plan(self.store, "block", expected["prompt"], True, "attack-01")
        self.assertEqual(plan, expected)
        self.assertEqual(stub["attack_tools"], sorted(test.get("attack_tools", [])))

    def test_typed_prompt_uses_base_tools_and_action_model(self):
        _, plan = lc.probe_plan(self.store, "alert", "hello", False, None)
        self.assertEqual(plan["tools"], list(dict.fromkeys(self.store.get("tools", []))))
        self.assertEqual(plan["system_prompt"], "")
        self.assertEqual(plan["model"], lc.model_for(self.store, "alert").get("public_name", ""))

    def test_observe_reports_most_severe_verdict_ungraded(self):
        result = lc.observe(execution="completed", verdict_rows=[{"verdict": "log"}, {"verdict": "block"}],
                            requests_sent=2, evidence=["block-message-in-reply"], tools_called=[], test={})
        self.assertEqual((result["outcome"], result["verdict"], result["reasons"]), ("observed", "block", []))
        partial = lc.observe(execution="completed", verdict_rows=[{"verdict": "alert"}], requests_sent=2, evidence=[])
        self.assertEqual(partial["verdict"], "alert")
        self.assertIn("1 of 2", partial["reasons"][0])
        failed = lc.observe(execution="error", verdict_rows=[], requests_sent=0, evidence=[])
        self.assertEqual(failed["verdict"], "unknown")
        self.assertTrue(failed["reasons"])

    def test_probe_runs_through_run_case_with_marker(self):
        logs, seen = Logs(["log", "alert"], key="student03_fortistore-injection_alert"), {}

        def agent(spec):
            seen.update(spec)
            logs.prompt = spec["prompt"]
            return {"reply": "ok", "tool_events": [], "rounds": 1, "error": None, "http_status": 200}
        stub, plan = lc.probe_plan(self.store, "alert", "hello", False, None)
        result = lc.run_case(agent=agent, fetch_logs=logs, evaluate=lc.observe, contains_sensitive=lambda _: False,
                             test=stub, plan=plan, key={"key_name": "student03_fortistore-injection_alert",
                                                         "secret": "faig_x"},
                             faig_url="http://faig", mcp_url="http://mcp", scenario_version="1",
                             sleep=lambda _: None, clock=lambda: 1000.0, log_wait=0)
        self.assertEqual((result["outcome"], result["verdict"]), ("observed", "alert"))
        self.assertTrue(lc.MARKER.search(seen["prompt"]))
        self.assertTrue(seen["prompt"].startswith("hello"))


if __name__ == "__main__":
    unittest.main()
