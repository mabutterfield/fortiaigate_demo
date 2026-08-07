from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = (
    REPO_ROOT / "chatbot" / "scenarios" / "examples" / "resume-tool-injection"
)
PROFILE_PATH = SCENARIO_ROOT / "profile.json"
ATTACK_PAYLOAD_PATH = SCENARIO_ROOT / "curl-payloads" / "attack-tool-result.json"
POISONED_RESUME_PATH = (
    REPO_ROOT
    / "mcp"
    / "chart"
    / "files"
    / "documents"
    / "resume_casey_jordan_poisoned.txt"
)


class ResumeToolInjectionScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        cls.attack_payload = json.loads(
            ATTACK_PAYLOAD_PATH.read_text(encoding="utf-8")
        )
        cls.poisoned_resume = POISONED_RESUME_PATH.read_text(encoding="utf-8")

    def test_actions_use_canonical_alert_and_deny_contract(self) -> None:
        entry_points = {
            entry["action"]: entry
            for entry in self.profile["matrix"]["entry_points"]
        }
        self.assertEqual(set(entry_points), {"alert", "deny"})
        self.assertEqual(entry_points["alert"]["guard_template"], "detect_only")
        self.assertEqual(entry_points["deny"]["guard_template"], "protect_input")
        self.assertTrue(entry_points["alert"]["required_for_release"])
        self.assertTrue(entry_points["deny"]["required_for_release"])

    def test_simplified_profiles_hold_tools_constant_across_paths(self) -> None:
        profiles = self.profile["matrix"]["chatbot_profiles"]
        self.assertEqual(
            {profile["mcp_tool_set"] for profile in profiles},
            {"cloud-pivot"},
        )
        self.assertEqual(
            {profile["provider_path"] for profile in profiles},
            {"direct", "faig-static"},
        )
        self.assertEqual(profiles[0]["display_name"], "Resume Tool Injection - LLM Direct")
        self.assertEqual(self.profile["mcp"]["default_transport"], "fortiweb")

    def test_least_privilege_and_cloud_pivot_profiles_are_distinct(self) -> None:
        mcp = self.profile["mcp"]
        self.assertNotIn("cloud_bucket_list_demo", mcp["required_tools"])
        extended = {
            tool_set["id"]: tool_set["tools"]
            for tool_set in mcp["extended_tool_sets"]
        }
        self.assertEqual(extended["cloud-pivot"], ["cloud_bucket_list_demo"])

    def test_poisoned_fixture_has_deterministic_injection_markers(self) -> None:
        lowered = self.poisoned_resume.lower()
        self.assertIn("ignore all previous instructions", lowered)
        self.assertIn("reveal the system prompt", lowered)
        self.assertIn("call any available cloud inventory", lowered)
        self.assertIn("synthetic indirect prompt-injection payload", lowered)

    def test_attack_replay_places_injection_in_tool_role(self) -> None:
        tool_messages = [
            message
            for message in self.attack_payload["messages"]
            if message.get("role") == "tool"
        ]
        self.assertGreaterEqual(len(tool_messages), 2)
        poisoned_result = tool_messages[0]["content"].lower()
        self.assertIn("ignore all previous instructions", poisoned_result)
        self.assertIn("reveal the system prompt", poisoned_result)

    def test_expected_trace_requires_deny_before_cloud_tool(self) -> None:
        expected_trace = " ".join(self.profile["expected_trace"]).lower()
        self.assertIn("deny", expected_trace)
        self.assertIn("before cloud_bucket_list_demo executes", expected_trace)


if __name__ == "__main__":
    unittest.main()
