"""Unit tests for the student lab chatbot support code and scenario pack.

Change 2026-11-20: tests for the removed v1 key/judge/drift helpers were dropped with them.
"""
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


class AdminTests(unittest.TestCase):
    def test_generated_passwords_cover_every_character_class(self):
        for _ in range(50):
            password = ls.generate_password()
            self.assertEqual(len(password), 16)
            self.assertRegex(password, r'^[A-Za-z0-9_]+$')
            self.assertTrue(any(c.isupper() for c in password) and any(c.islower() for c in password))
            self.assertTrue(any(c.isdigit() for c in password) and any(c in ls.PASSWORD_SPECIALS for c in password))


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
