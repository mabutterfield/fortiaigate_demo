from __future__ import annotations

import unittest

from scripts import scenario_test_harness


class ScenarioTestHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = {
            "global": {"passthrough_model_alias": "pass-model"},
            "chatbot_faig_static_routes": [
                {
                    "name": "hr-tool-dlp-output-dlp-redact",
                    "label": "HR Output Redact",
                    "model": "hr-tool-dlp",
                    "role": "output-dlp-redact",
                    "scenario_id": "hr-tool-dlp",
                }
            ],
            "chatbot_simplified_profiles": [
                {
                    "id": "hr-tool-dlp-direct",
                    "provider_path": "direct",
                    "scenario_id": "hr-tool-dlp",
                    "model": "hr-tool-dlp",
                    "mcp_enabled": True,
                    "mcp_path": "direct",
                    "mcp_tool_profile": "hr-tool-dlp",
                    "mcp_max_tool_rounds": 5,
                    "frontend_instruction_profile": "none",
                },
                {
                    "id": "hr-tool-dlp-output-redact",
                    "provider_path": "faig-static",
                    "route": "hr-tool-dlp-output-dlp-redact",
                    "scenario_id": "hr-tool-dlp",
                    "model": "hr-tool-dlp",
                    "mcp_enabled": True,
                    "mcp_path": "direct",
                    "mcp_tool_profile": "hr-tool-dlp",
                    "mcp_max_tool_rounds": 5,
                    "frontend_instruction_profile": "none",
                },
            ],
        }

    def test_path_role_resolves_scenario_route_and_profile(self) -> None:
        config = scenario_test_harness.scenario_path_configs(
            self.matrix,
            "hr-tool-dlp",
            ["output-dlp-redact"],
        )[0]
        self.assertEqual(config["route"], "hr-tool-dlp-output-dlp-redact")
        self.assertEqual(config["model"], "hr-tool-dlp")
        self.assertEqual(config["tool_profile"], "hr-tool-dlp")
        self.assertEqual(config["max_tool_rounds"], 5)

    def test_direct_and_passthrough_are_canonical_controls(self) -> None:
        direct, passthrough = scenario_test_harness.scenario_path_configs(
            self.matrix,
            "hr-tool-dlp",
            ["direct", "passthrough"],
        )
        self.assertEqual(direct["model"], "hr-tool-dlp")
        self.assertTrue(direct["mcp_enabled"])
        self.assertEqual(passthrough["route"], "passthrough")
        self.assertEqual(passthrough["model"], "pass-model")
        self.assertFalse(passthrough["mcp_enabled"])

    def test_unknown_role_lists_available_roles(self) -> None:
        with self.assertRaisesRegex(SystemExit, "Available: direct"):
            scenario_test_harness.scenario_path_configs(
                self.matrix,
                "hr-tool-dlp",
                ["missing-role"],
            )


if __name__ == "__main__":
    unittest.main()
