"""Unit tests for the student lab chatbot support code and scenario pack."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
KEY = b"unit-test-key"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ls = load("lab_support", "chatbot/lab-chatbot/chart/files/lab_support.py")
lab_auth = load("lab_auth_for_chatbot", "chatbot/https-gateway/chart/files/lab_auth.py")
IDENTITY = {"user": "student02@fortiai.lab", "student": "student02", "role": "student", "workspace_id": "ws-2", "ts": "1000"}
KEYS = [
    {"keyName": "student02-hr-tool-dlp-redact", "scenario": "hr-tool-dlp", "action": "redact", "model": "hr-tool-dlp",
     "secretKey": "faig_secret_value_1234"},
    {"keyName": "student02-passthrough", "scenario": "passthrough", "action": "passthrough", "model": "pass-model",
     "secretKey": "faig_secret_value_9999"},
]
PACK = {"scenarios": {"hr-tool-dlp": {"actions": {"redact": {}, "deny": {}}},
                      "passthrough": {"actions": {"passthrough": {}}},
                      "resume-tool-injection": {"actions": {"alert": {}}}}}


def lower(headers):
    return {k.lower(): v for k, v in headers.items()}


class IdentityTests(unittest.TestCase):
    def test_gateway_signature_verifies_in_chatbot(self):
        headers = lower(lab_auth_headers(IDENTITY))
        self.assertEqual(ls.verify_identity(headers, KEY, now=1100)["student"], "student02")

    def test_chatbot_resigned_headers_verify_in_gateway(self):
        headers = lower(ls.identity_headers(IDENTITY, KEY, now=5000))
        self.assertEqual(headers["x-lab-ts"], "5000")
        self.assertEqual(lab_auth.verify_identity(headers, KEY, now=5010)["user"], IDENTITY["user"])

    def test_rejects_tampering_staleness_and_unknown_roles(self):
        headers = lower(lab_auth_headers(IDENTITY))
        self.assertIsNone(ls.verify_identity({**headers, "x-lab-student": "student01"}, KEY, now=1100))
        self.assertIsNone(ls.verify_identity(headers, KEY, now=1000 + ls.SIGNATURE_MAX_AGE + 1))
        self.assertIsNone(ls.verify_identity(lower(lab_auth_headers({**IDENTITY, "role": "viewer"})), KEY, now=1100))
        self.assertIsNone(ls.verify_identity({}, KEY, now=1100))


def lab_auth_headers(identity):
    out = {"X-Lab-" + "-".join(p.capitalize() for p in f.split("_")): identity[f] for f in lab_auth.IDENTITY_FIELDS}
    out["X-Lab-Signature"] = lab_auth.sign_identity(identity, KEY)
    return out


class KeyTests(unittest.TestCase):
    def test_available_only_lists_actions_with_keys(self):
        self.assertEqual(ls.available(KEYS, PACK), {"hr-tool-dlp": ["redact"], "passthrough": ["passthrough"]})

    def test_public_rows_never_include_secrets(self):
        rows = ls.public_keys(KEYS)
        self.assertNotIn("faig_secret_value", json.dumps(rows))
        self.assertEqual(rows[0]["secret"], "...1234")

    def test_replace_secret_updates_one_key(self):
        updated = ls.replace_secret(KEYS, "student02-passthrough", " new_value_abcdef ", "admin@lab", now=0)
        self.assertEqual(updated[1]["secretKey"], "new_value_abcdef")
        self.assertEqual(updated[1]["updatedBy"], "admin@lab")
        self.assertEqual(updated[0], KEYS[0])
        with self.assertRaises(ValueError):
            ls.replace_secret(KEYS, "student02-passthrough", "has space", "u")
        with self.assertRaises(KeyError):
            ls.replace_secret(KEYS, "missing", "value_value", "u")


SPEC = {"model": "hr-tool-dlp", "system_prompt": "", "tools": ["employee_sensitive_lookup"], "max_rounds": 3,
        "test": {"prompt": "Get sensitive information for employee EMP-5001.", "expected_result": "redacted",
                 "required_tools": ["employee_sensitive_lookup"], "forbidden_tools": [],
                 "expected_log_verdict": "Redact"}}
REDACTED_TURN = {"reply": "SSN: [REDACTED_SSN_1]", "tool_events": [{"tool": "employee_sensitive_lookup", "result": {}}],
                 "exchanges": [{"round": 0, "request": {}, "status": 200, "response": {}},
                               {"round": 1, "request": {}, "status": 200, "response": {}}]}


class FakeLogs:
    def __init__(self, batches, status=200):
        self.batches, self.status, self.calls, self.spec_seen = list(batches), status, [], None

    def __call__(self, **query):
        self.calls.append(query)
        if self.status != 200:
            return self.status, {"error": "invalid or expired identity"}
        if query.get("uuid"):
            return 200, {"uuid": query["uuid"], "verdictLabel": "Redact", "toolDefinitions": ["big"],
                         "prompt": {"original": "p"}}
        rows = self.batches.pop(0) if len(self.batches) > 1 else self.batches[0]
        return 200, {"items": rows}


class RunTestTests(unittest.TestCase):
    def run_case(self, turn, logs, **kwargs):
        seen = {}

        def agent(spec):
            seen.update(spec)
            return dict(turn)

        result = ls.run_test(agent, logs, scenario="hr-tool-dlp", action="redact", spec=SPEC, key=KEYS[0],
                             faig_url="http://faig/ai/openai/v1", mcp_url="http://mcp/mcp", sleep=lambda _: None,
                             clock=lambda: 1000.0, **kwargs)
        return result, seen

    def test_pass_with_logs_waits_for_one_row_per_request(self):
        logs = FakeLogs([[{"uuid": "b", "timeStamp": 2, "verdictLabel": "Log"}],
                         [{"uuid": "b", "timeStamp": 2, "verdictLabel": "Log"},
                          {"uuid": "a", "timeStamp": 1, "verdictLabel": "Redact"}]])
        result, spec = self.run_case(REDACTED_TURN, logs)
        self.assertTrue(result["passed"], result["details"])
        self.assertTrue(spec["record_exchanges"])
        self.assertEqual(logs.calls[0], {"key_alias": "student02-hr-tool-dlp-redact", "since_ms": 998000})
        self.assertEqual([e["uuid"] for e in result["log_entries"]], ["a", "b"])
        self.assertNotIn("toolDefinitions", result["log_entries"][0])
        self.assertNotIn("faig_secret_value", json.dumps(result))

    def test_wrong_log_verdict_fails(self):
        logs = FakeLogs([[{"uuid": "a", "timeStamp": 1, "verdictLabel": "Log"},
                          {"uuid": "b", "timeStamp": 2, "verdictLabel": "Log"}]])
        result, _ = self.run_case(REDACTED_TURN, logs, with_details=False)
        self.assertFalse(result["passed"])
        self.assertIn("Traffic Log verdict Log", result["details"][-1])
        self.assertEqual(result["log_entries"], [])

    def test_unavailable_log_judges_response_only(self):
        result, _ = self.run_case(REDACTED_TURN, FakeLogs([[]], status=403))
        self.assertTrue(result["passed"])
        self.assertIsNone(result["verdicts"])
        self.assertIn("Traffic Log not checked", result["details"][-1])

    def test_unredacted_reply_fails_contract(self):
        turn = dict(REDACTED_TURN, reply="SSN: 489-36-8350")
        logs = FakeLogs([[{"uuid": "a", "timeStamp": 1, "verdictLabel": "Redact"},
                          {"uuid": "b", "timeStamp": 2, "verdictLabel": "Redact"}]])
        result, _ = self.run_case(turn, logs)
        self.assertFalse(result["passed"])
        self.assertIn("expected redacted scenario verdict", result["details"])


class AdminTests(unittest.TestCase):
    def test_generated_passwords_cover_every_character_class(self):
        for _ in range(50):
            password = ls.generate_password()
            self.assertEqual(len(password), 16)
            self.assertTrue(any(c.isupper() for c in password) and any(c.islower() for c in password))
            self.assertTrue(any(c.isdigit() for c in password) and any(c in ls.PASSWORD_SPECIALS for c in password))

    def test_drift_and_restore(self):
        seed = [dict(k) for k in KEYS]
        current = [dict(KEYS[0], secretKey="student_replaced_value", updatedBy="student02@fortiai.lab")]
        rows = {r["key"]: r for r in ls.key_drift(current + [{"keyName": "extra", "secretKey": "x"}], seed)}
        self.assertEqual(rows["student02-hr-tool-dlp-redact"]["status"], "changed")
        self.assertEqual(rows["student02-passthrough"]["status"], "missing (seed only)")
        self.assertEqual(rows["extra"]["status"], "not in seed")
        self.assertNotIn("secret", json.dumps(list(rows.values())).replace('"status"', ""))
        restored = ls.restore_keys(current, seed, ["student02-hr-tool-dlp-redact", "student02-passthrough"])
        self.assertEqual([k["secretKey"] for k in restored], [KEYS[0]["secretKey"], KEYS[1]["secretKey"]])
        self.assertEqual({r["status"] for r in ls.key_drift(restored, seed)}, {"matches seed"})
        with self.assertRaises(KeyError):
            ls.restore_keys(current, seed, ["nope"])


class ScenarioPackTests(unittest.TestCase):
    def test_pack_has_no_secrets_and_one_entry_per_action(self):
        from functional_test import scenario_pack

        keys = [dict(k) for k in KEYS] + [dict(KEYS[1], student="student01")]
        cases = []

        def fake_plan(matrix, store, key):
            cases.append(key["keyName"])
            return {"case_id": "c", "prompt": "p", "model": key["model"], "system_prompt": "", "tools": [],
                    "max_rounds": 0, "expected_result": "completed", "required_tools": [], "forbidden_tools": []}

        original_plan, original_info = scenario_pack.baseline.plan_case, scenario_pack.scenario_info
        scenario_pack.baseline.plan_case = fake_plan
        scenario_pack.scenario_info = lambda store, s: {"title": s, "description": "", "sample_prompts": {}}
        try:
            pack = scenario_pack.build_pack({}, None, keys)
        finally:
            scenario_pack.baseline.plan_case, scenario_pack.scenario_info = original_plan, original_info
        self.assertEqual(len(cases), 2)
        self.assertEqual(pack["scenarios"]["hr-tool-dlp"]["actions"]["redact"]["test"]["expected_log_verdict"], "Redact")
        self.assertNotIn("faig_secret_value", json.dumps(pack))


if __name__ == "__main__":
    unittest.main()
