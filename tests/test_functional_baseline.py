"""Unit tests for the chatbot-free 8.0.2 baseline (functional_test/baseline.py)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from functional_test import baseline  # noqa: E402

MATRIX = {
    "chatbot_simplified_profiles": [
        {"id": "hr-tool-dlp-redact", "scenario_id": "hr-tool-dlp", "provider_path": "faig-static",
         "route": "hr-tool-dlp-redact", "mcp_enabled": True, "mcp_tool_profile": "hr-tool-dlp",
         "mcp_max_tool_rounds": 8, "frontend_instruction_profile": "none"},
        {"id": "fortistore-injection-deny-no-frontend", "scenario_id": "fortistore-injection",
         "provider_path": "faig-static", "route": "fortistore-injection-deny", "mcp_enabled": False},
        {"id": "fortistore-injection-deny", "scenario_id": "fortistore-injection", "provider_path": "faig-static",
         "route": "fortistore-injection-deny", "mcp_enabled": False,
         "frontend_instruction_profile": "fortistore-injection-compromised"},
    ],
    "chatbot_mcp_tool_profiles": [{"name": "hr-tool-dlp", "tools": ["employee_lookup", "employee_sensitive_lookup"]}],
}


class BaselinePlanningTests(unittest.TestCase):
    def test_environment_selects_student_key_directories_and_admin(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "students" / "student01-keys").mkdir(parents=True)
            (root / "students" / "student02-keys").mkdir()
            with patch.dict("os.environ", {"FAIG_ENV_DIR": temp}):
                args = baseline.parse_args([])
                self.assertEqual(args.key_dir, [root / "students/student01-keys", root / "students/student02-keys"])
                self.assertEqual(args.admin_credentials, root / "admin-login.json")
                explicit = baseline.parse_args(["--key-dir", "/private/alternate"])
                self.assertEqual(explicit.key_dir, [Path("/private/alternate")])

    def test_action_profile_prefers_canonical_id(self):
        self.assertEqual(baseline.action_profile(MATRIX, "fortistore-injection", "deny")["id"],
                         "fortistore-injection-deny")
        with self.assertRaises(SystemExit):
            baseline.action_profile(MATRIX, "fortistore-injection", "redact")

    def test_tool_names_from_profile(self):
        self.assertEqual(baseline.tool_names(MATRIX, "hr-tool-dlp"), ["employee_lookup", "employee_sensitive_lookup"])
        self.assertEqual(baseline.tool_names(MATRIX, ""), [])
        with self.assertRaises(SystemExit):
            baseline.tool_names(MATRIX, "missing")

    def test_passthrough_case_needs_no_scenario(self):
        case = baseline.plan_case(MATRIX, None, {"keyName": "student01-passthrough", "student": "student01",
                                                 "scenario": "passthrough", "action": "passthrough",
                                                 "model": "pass-model"})
        self.assertEqual((case["expected_result"], case["tools"], case["max_rounds"]), ("completed", [], 0))

    def test_key_files_must_be_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            directory.chmod(0o700)
            path = directory / "k.json"
            path.write_text(json.dumps({"keyName": "k", "scenario": "passthrough", "action": "passthrough",
                                        "model": "pass-model", "secretKey": "x"}))
            path.chmod(0o600)
            self.assertEqual(baseline.key_files([directory])[0]["keyName"], "k")
            path.chmod(0o644)
            with self.assertRaises(SystemExit):
                baseline.key_files([directory])


class BaselineJudgeTests(unittest.TestCase):
    CASE = {"scenario": "hr-tool-dlp", "action": "redact", "expected_result": "redacted",
            "required_tools": ["employee_sensitive_lookup"], "forbidden_tools": []}

    def raw(self, reply, tools=("employee_sensitive_lookup",)):
        return {"reply": reply, "tool_events": [{"tool": t, "result": {}} for t in tools]}

    def test_8_0_2_redaction_marker_and_log_verdict(self):
        ok, details, normalized = baseline.judge(self.CASE, self.raw("SSN [REDACTED_SSN_1]"), ["Log", "Redact"])
        self.assertTrue(ok, details)
        self.assertEqual(normalized["scenario_verdict"], "redacted")

    def test_wrong_log_verdict_fails_even_when_reply_matches(self):
        ok, details, _ = baseline.judge(self.CASE, self.raw("SSN [REDACTED_SSN_1]"), ["Log"])
        self.assertFalse(ok)
        self.assertIn("expected Redact", details[-1])

    def test_missing_required_tool_fails(self):
        ok, details, _ = baseline.judge(self.CASE, self.raw("SSN [REDACTED_SSN_1]", tools=()), None)
        self.assertFalse(ok)
        self.assertTrue(any("missing required tools" in d for d in details))

    def test_agent_error_is_reported(self):
        ok, details, _ = baseline.judge(self.CASE, {"error": "faig_http_error", "detail": {"x": 1},
                                                    "reply": "", "tool_events": []}, None)
        self.assertFalse(ok)
        self.assertTrue(details[0].startswith("faig_http_error"))


if __name__ == "__main__":
    unittest.main()
